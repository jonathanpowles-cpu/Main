"""Shareable food and recipe links for the MyFitnessPal phone app.

``FoodLinks.make`` turns a :class:`FoodSpec` into a short signed URL such as
``https://host/food/z…``. Nothing is stored: the food is encoded in the link
itself. Opening the link shows a phone-friendly page that

* carries schema.org ``Recipe`` JSON-LD (ingredients, yield and nutrition), so
  the MyFitnessPal app's *Recipes → Import from web* can read it, and
* has an *Add to MyFitnessPal* button that creates the food as a private
  custom food through :class:`MFPClient`, after asking for the connector
  password. The food then appears under *My Foods* in the app.

``FoodLinks.make_recipe`` does the same for a :class:`RecipeSpec` at
``https://host/recipe/z…``. That page exists purely to be scraped: it is a
plain ingredient list with no scripts, no images and no layout, marked up
three ways at once (JSON-LD, schema.org microdata and legacy hRecipe classes)
because MyFitnessPal's importer is old and picks whichever it recognises.

The two pages answer different questions, and it is worth keeping them apart.
MyFitnessPal's importer *never* reads a page's published nutrition: it matches
each ingredient line against its own food database and adds the results up.
So ``/recipe`` gives you MyFitnessPal's estimate for a dish, and ``/food``
gives you the label's exact numbers. A recipe page with nutrition attached
links to its food page for that reason.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from .auth import PasswordAuthProvider, page
from .mfp_client import FoodSpec, MFPClient, MFPError, manual_entry
from .nutrition import NutritionFacts

# NutritionFacts field -> schema.org NutritionInformation property and unit
_SCHEMA_NUTRIENTS: list[tuple[str, str, str]] = [
    ("fat_g", "fatContent", "g"),
    ("saturated_fat_g", "saturatedFatContent", "g"),
    ("trans_fat_g", "transFatContent", "g"),
    ("cholesterol_mg", "cholesterolContent", "mg"),
    ("sodium_mg", "sodiumContent", "mg"),
    ("carbohydrates_g", "carbohydrateContent", "g"),
    ("fibre_g", "fiberContent", "g"),
    ("sugars_g", "sugarContent", "g"),
    ("protein_g", "proteinContent", "g"),
]


@dataclass
class RecipeSpec:
    """A recipe as MyFitnessPal's importer wants to see it.

    Only ``name`` and ``ingredients`` matter to the importer, and the
    ingredient lines should read like a shopping list — ``"330 g chicken
    breast"``, not ``"chicken"`` or ``"1 packet chicken"`` — because each line
    is matched against the food database on its own. ``nutrition`` is the
    label's own per-serving figures, which MyFitnessPal ignores; it is carried
    so the page can also offer them as an exact custom food.
    """

    name: str
    ingredients: list[str]
    servings: float = 1.0
    instructions: list[str] = field(default_factory=list)
    description: str | None = None
    author: str | None = None
    source_url: str | None = None
    nutrition: NutritionFacts | None = None


class FoodLinks:
    def __init__(
        self,
        auth: PasswordAuthProvider,
        client_factory: Callable[[], MFPClient] = MFPClient.from_env,
    ) -> None:
        self.auth = auth
        self.public_url = auth.public_url
        self.client_factory = client_factory

    # -- encode / decode ---------------------------------------------------------

    def make(self, spec: FoodSpec, ingredients: list[str] | None = None) -> str:
        payload = {
            "k": "food",
            "n": spec.name,
            "b": spec.brand,
            "s": spec.serving_description,
            "q": spec.serving_quantity,
            "c": spec.country_code,
            "nu": {key: value for key, value in spec.nutrition.to_dict().items() if value is not None},
            "i": [line.strip() for line in (ingredients or []) if line.strip()],
        }
        return f"{self.public_url}/food/{self.auth.signer.sign(payload, compress=True)}"

    def load(self, token: str) -> tuple[FoodSpec, list[str]] | None:
        payload = self.auth.signer.verify(token, "food")
        if payload is None:
            return None
        spec = FoodSpec(
            name=payload["n"],
            nutrition=NutritionFacts(**payload["nu"]),
            brand=payload.get("b"),
            serving_description=payload.get("s", "serving"),
            serving_quantity=payload.get("q", 1.0),
            country_code=payload.get("c", "AU"),
        )
        return spec, list(payload.get("i", []))

    def make_recipe(self, spec: RecipeSpec) -> str:
        # Omit empty fields rather than signing nulls: the whole recipe travels
        # in the URL, so every byte saved is a shorter thing to paste.
        payload: dict[str, Any] = {
            "k": "recipe",
            "n": spec.name,
            "y": spec.servings,
            "i": [line.strip() for line in spec.ingredients if line.strip()],
        }
        for key, value in (("d", spec.instructions), ("de", spec.description),
                           ("a", spec.author), ("u", spec.source_url)):
            if value:
                payload[key] = [line.strip() for line in value if line.strip()] if key == "d" else value
        if spec.nutrition is not None:
            payload["nu"] = {k: v for k, v in spec.nutrition.to_dict().items() if v is not None}
        return f"{self.public_url}/recipe/{self.auth.signer.sign(payload, compress=True)}"

    def load_recipe(self, token: str) -> RecipeSpec | None:
        payload = self.auth.signer.verify(token, "recipe")
        if payload is None:
            return None
        return RecipeSpec(
            name=payload["n"],
            ingredients=list(payload.get("i", [])),
            servings=payload.get("y", 1.0),
            instructions=list(payload.get("d", [])),
            description=payload.get("de"),
            author=payload.get("a"),
            source_url=payload.get("u"),
            nutrition=NutritionFacts(**payload["nu"]) if payload.get("nu") else None,
        )

    # -- HTTP -----------------------------------------------------------------------

    async def food_page(self, request: Request) -> Response:
        loaded = self.load(request.path_params["token"])
        if loaded is None:
            return HTMLResponse(page("<h1>Not found</h1><p>This food link is invalid.</p>"), 404)
        spec, ingredients = loaded
        return HTMLResponse(render_food_page(spec, ingredients, str(request.url)))

    async def recipe_page(self, request: Request) -> Response:
        spec = self.load_recipe(request.path_params["token"])
        if spec is None:
            return HTMLResponse(page("<h1>Not found</h1><p>This recipe link is invalid.</p>"), 404)
        food_url = None
        if spec.nutrition is not None:
            # Re-derive rather than store: the food link is a pure function of
            # the recipe, so the two pages can never drift apart.
            food_url = self.make(
                FoodSpec(name=spec.name, nutrition=spec.nutrition, brand=spec.author),
                spec.ingredients,
            )
        return HTMLResponse(render_recipe_page(spec, str(request.url), food_url))

    async def add_food(self, request: Request) -> Response:
        loaded = self.load(request.path_params["token"])
        if loaded is None:
            return HTMLResponse(page("<h1>Not found</h1><p>This food link is invalid.</p>"), 404)
        spec, ingredients = loaded
        form = await request.form()
        page_url = str(request.url).removesuffix("/add")
        if not self.auth.check_password(str(form.get("password", ""))):
            return HTMLResponse(render_food_page(spec, ingredients, page_url, error="Wrong password."), 401)
        try:
            result = self.client_factory().create_food(spec)
        except MFPError as exc:
            return HTMLResponse(render_food_page(spec, ingredients, page_url, error=str(exc)), 502)
        return HTMLResponse(
            page(
                f"<h1>Added to MyFitnessPal</h1><p><b>{html.escape(spec.name)}</b> is now in <i>My Foods</i> "
                f"in the app (food id {html.escape(str(result.get('id') or '?'))}). "
                f"Search for it by name when logging a meal.</p>"
                f"<p><a href='{html.escape(page_url)}'>Back</a></p>"
            )
        )


# -- rendering ---------------------------------------------------------------


def _nutrition_schema(facts: NutritionFacts, serving_size: str) -> dict[str, Any]:
    nutrition: dict[str, Any] = {
        "@type": "NutritionInformation",
        "calories": f"{round(facts.calories)} calories",
        "servingSize": serving_size,
    }
    for field_name, prop, unit in _SCHEMA_NUTRIENTS:
        value = getattr(facts, field_name)
        if value is not None:
            nutrition[prop] = f"{value:g} {unit}"
    return nutrition


def _script(data: dict[str, Any]) -> str:
    # "</" inside a <script> would end the element early, whatever follows it.
    escaped = json.dumps(data).replace("</", "<\\/")
    return f"<script type='application/ld+json'>{escaped}</script>"


def recipe_json_ld(spec: FoodSpec, ingredients: list[str], url: str) -> dict[str, Any]:
    serving = f"{spec.serving_quantity:g} {spec.serving_description}"
    title = f"{spec.brand} {spec.name}".strip() if spec.brand else spec.name
    return {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": title,
        "url": url,
        "author": {"@type": "Organization", "name": spec.brand or "Custom"},
        "recipeYield": serving,
        "recipeIngredient": ingredients or [f"{serving} {title}"],
        "recipeInstructions": [{"@type": "HowToStep", "text": "Nutrition is per serving as printed on the label."}],
        "nutrition": _nutrition_schema(spec.nutrition, serving),
    }


def render_food_page(spec: FoodSpec, ingredients: list[str], url: str, error: str | None = None) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(str(row['field']))}</td><td>{html.escape(str(row['value']))}</td></tr>"
        for row in manual_entry(spec)[3:]
    )
    ingredient_html = (
        "<h2>Ingredients</h2><ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in ingredients) + "</ul>"
        if ingredients
        else ""
    )
    title = html.escape(spec.name)
    brand = f"<p>{html.escape(spec.brand)}</p>" if spec.brand else ""
    err = f"<p class='err'>{html.escape(error)}</p>" if error else ""
    serving = f"Per {spec.serving_quantity:g} {html.escape(spec.serving_description)}"
    weight = spec.nutrition.serving_weight_g
    if weight:
        # The label rarely prints the serving weight, so show the derived one:
        # it tells the reader whether their portion matched the card.
        serving += f" ({weight:g} g)"
    body = (
        f"<h1>{title}</h1>{brand}"
        f"<p>{serving}</p>"
        f"<table>{rows}</table>{ingredient_html}"
        f"<h2>Add to MyFitnessPal</h2>{err}"
        f"<form method='post' action='{html.escape(url)}/add'>"
        f"<input type='password' name='password' placeholder='Connector password' required>"
        f"<button type='submit'>Add to My Foods</button></form>"
        f"<p><small>Or in the MyFitnessPal app: Recipes → Create a Recipe → Import from web, and paste this page's link.</small></p>"
    )
    head_extra = _script(recipe_json_ld(spec, ingredients, url))
    return page(body, title=spec.name).replace("</head>", f"{head_extra}<style>table{{width:100%;border-collapse:collapse}}td{{padding:.3rem 0;border-bottom:1px solid #2a2a2a}}td:last-child{{text-align:right}}h2{{font-size:1rem;margin-top:1.5rem}}</style></head>")


def recipe_page_json_ld(spec: RecipeSpec, url: str) -> dict[str, Any]:
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": spec.name,
        "url": url,
        "recipeYield": f"{spec.servings:g} serving{'' if spec.servings == 1 else 's'}",
        "recipeIngredient": list(spec.ingredients),
        "recipeInstructions": [{"@type": "HowToStep", "text": step} for step in spec.instructions],
    }
    if spec.description:
        data["description"] = spec.description
    if spec.author:
        data["author"] = {"@type": "Organization", "name": spec.author}
    if spec.source_url:
        data["isBasedOn"] = spec.source_url
    if spec.nutrition is not None:
        data["nutrition"] = _nutrition_schema(spec.nutrition, "1 serving")
    return data


_RECIPE_STYLE = (
    "main{width:min(560px,92vw)}"
    "ul,ol{padding-left:1.2rem}li{margin:.35rem 0}"
    "h2{font-size:1rem;margin:1.5rem 0 .5rem}"
    "textarea{width:100%;box-sizing:border-box;height:9rem;background:#111;color:#eee;"
    "border:1px solid #444;border-radius:8px;padding:.6rem;font:14px/1.5 ui-monospace,monospace}"
    "a{color:#93c5fd}"
)


def render_recipe_page(spec: RecipeSpec, url: str, food_url: str | None = None) -> str:
    """A deliberately plain recipe page for MyFitnessPal's importer.

    No scripts, no images, no wrapper markup. The ingredients are marked up
    three ways — JSON-LD, schema.org microdata and hRecipe class names —
    because different scrapers look for different ones and there is no cost
    to satisfying all three.
    """
    yield_text = f"{spec.servings:g} serving{'' if spec.servings == 1 else 's'}"
    ingredients = "".join(
        f"<li class='ingredient' itemprop='recipeIngredient'>{html.escape(line)}</li>" for line in spec.ingredients
    )
    steps = (
        "<h2>Method</h2><ol class='instructions' itemprop='recipeInstructions'>"
        + "".join(f"<li class='instruction'>{html.escape(step)}</li>" for step in spec.instructions)
        + "</ol>"
        if spec.instructions
        else ""
    )
    summary = f"<p class='summary' itemprop='description'>{html.escape(spec.description)}</p>" if spec.description else ""
    author = f"<p class='author' itemprop='author'>{html.escape(spec.author)}</p>" if spec.author else ""
    source = (
        f"<p><small>Adapted from <a href='{html.escape(spec.source_url)}'>{html.escape(spec.source_url)}</a></small></p>"
        if spec.source_url
        else ""
    )
    exact = (
        f"<h2>Exact label numbers</h2><p>MyFitnessPal works out its own nutrition from the ingredient lines above. "
        f"For the figures printed on the card instead, use <a href='{html.escape(food_url)}'>the custom food</a>.</p>"
        if food_url
        else ""
    )
    body = (
        f"<div class='hrecipe' itemscope itemtype='https://schema.org/Recipe'>"
        f"<h1 class='fn' itemprop='name'>{html.escape(spec.name)}</h1>"
        f"{summary}{author}"
        f"<p>Serves <span class='yield' itemprop='recipeYield'>{html.escape(yield_text)}</span></p>"
        f"<h2>Ingredients</h2><ul>{ingredients}</ul>"
        f"{steps}{source}</div>"
        f"<h2>Import into MyFitnessPal</h2>"
        f"<p>In the app: <i>Recipes → Import Recipe</i>, and paste this page's address.</p>"
        f"<p>If it refuses the link, tap <i>Enter Ingredients Manually</i> and paste this instead:</p>"
        f"<textarea readonly>{html.escape(chr(10).join(spec.ingredients))}</textarea>"
        f"{exact}"
    )
    head_extra = _script(recipe_page_json_ld(spec, url))
    return page(body, title=spec.name).replace("</head>", f"{head_extra}<style>{_RECIPE_STYLE}</style></head>")
