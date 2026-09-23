"""Shareable food links for the MyFitnessPal phone app.

``FoodLinks.make`` turns a :class:`FoodSpec` into a short signed URL such as
``https://host/food/z…``. Nothing is stored: the food is encoded in the link
itself. Opening the link shows a phone-friendly page that

* carries schema.org ``Recipe`` JSON-LD (ingredients, yield and nutrition), so
  the MyFitnessPal app's *Recipes → Import from web* can read it, and
* has an *Add to MyFitnessPal* button that creates the food as a private
  custom food through :class:`MFPClient`, after asking for the connector
  password. The food then appears under *My Foods* in the app.
"""

from __future__ import annotations

import html
import json
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

    # -- HTTP -----------------------------------------------------------------------

    async def food_page(self, request: Request) -> Response:
        loaded = self.load(request.path_params["token"])
        if loaded is None:
            return HTMLResponse(page("<h1>Not found</h1><p>This food link is invalid.</p>"), 404)
        spec, ingredients = loaded
        return HTMLResponse(render_food_page(spec, ingredients, str(request.url)))

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


def recipe_json_ld(spec: FoodSpec, ingredients: list[str], url: str) -> dict[str, Any]:
    facts = spec.nutrition
    nutrition: dict[str, Any] = {
        "@type": "NutritionInformation",
        "calories": f"{round(facts.calories)} calories",
        "servingSize": f"{spec.serving_quantity:g} {spec.serving_description}",
    }
    for field_name, prop, unit in _SCHEMA_NUTRIENTS:
        value = getattr(facts, field_name)
        if value is not None:
            nutrition[prop] = f"{value:g} {unit}"
    title = f"{spec.brand} {spec.name}".strip() if spec.brand else spec.name
    return {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": title,
        "url": url,
        "author": {"@type": "Organization", "name": spec.brand or "Custom"},
        "recipeYield": f"{spec.serving_quantity:g} {spec.serving_description}",
        "recipeIngredient": ingredients or [f"{spec.serving_quantity:g} {spec.serving_description} {title}"],
        "recipeInstructions": [{"@type": "HowToStep", "text": "Nutrition is per serving as printed on the label."}],
        "nutrition": nutrition,
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
    json_ld = json.dumps(recipe_json_ld(spec, ingredients, url)).replace("</", "<\\/")
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
    head_extra = f"<script type='application/ld+json'>{json_ld}</script>"
    return page(body).replace("</head>", f"{head_extra}<style>table{{width:100%;border-collapse:collapse}}td{{padding:.3rem 0;border-bottom:1px solid #2a2a2a}}td:last-child{{text-align:right}}h2{{font-size:1rem;margin-top:1.5rem}}</style></head>")
