"""Tests for shareable food links and their phone page."""

import json
import re

from starlette.testclient import TestClient

from connectors.myfitnesspal.auth import PasswordAuthProvider
from connectors.myfitnesspal.links import FoodLinks, render_food_page
from connectors.myfitnesspal.mfp_client import FoodSpec
from connectors.myfitnesspal.nutrition import NutritionFacts
from connectors.myfitnesspal.server import create_server

PUBLIC_URL = "http://localhost"
PASSWORD = "hunter2"
INGREDIENTS = ["3 cloves garlic", "20g butter", "1 packet basmati rice", "250g beef mince"]


class RecordingClient:
    specs = []

    def create_food(self, spec):
        RecordingClient.specs.append(spec)
        return {"id": "food-9", "description": spec.name, "brand": spec.brand, "item": {}}


def _spec():
    return FoodSpec(
        name="Beef & garlic rice bowl",
        brand="HelloFresh",
        nutrition=NutritionFacts(
            calories=641, protein_g=36.9, fat_g=22.2, saturated_fat_g=9.4, carbohydrates_g=70.7,
            sugars_g=9, sodium_mg=1580, fibre_g=8.5, energy_kj=2680, serving_weight_g=432,
        ),
    )


def _auth(secret="s"):
    return PasswordAuthProvider(PASSWORD, PUBLIC_URL, secret=secret)


def _client():
    from mcp.server.transport_security import TransportSecuritySettings

    server = create_server(client_factory=RecordingClient, auth=_auth())
    app = server.streamable_http_app(
        host="0.0.0.0",
        transport_security=TransportSecuritySettings(allowed_hosts=["localhost", "localhost:*"], allowed_origins=[PUBLIC_URL]),
    )
    return TestClient(app, base_url=PUBLIC_URL)


def test_link_round_trips_food_and_ingredients():
    links = FoodLinks(_auth(), client_factory=RecordingClient)
    url = links.make(_spec(), INGREDIENTS)
    assert url.startswith(f"{PUBLIC_URL}/food/z")
    assert len(url) < 600
    spec, ingredients = links.load(url.rsplit("/", 1)[1])
    assert spec.name == "Beef & garlic rice bowl"
    assert spec.nutrition == _spec().nutrition
    assert ingredients == INGREDIENTS
    assert FoodLinks(_auth("other"), client_factory=RecordingClient).load(url.rsplit("/", 1)[1]) is None


def test_food_page_has_recipe_json_ld_and_nutrients():
    url = FoodLinks(_auth(), client_factory=RecordingClient).make(_spec(), INGREDIENTS)
    with _client() as client:
        r = client.get(url)
        assert r.status_code == 200
        assert "Beef &amp; garlic rice bowl" in r.text and "250g beef mince" in r.text
        ld = json.loads(re.search(r"<script type='application/ld\+json'>(.*?)</script>", r.text, re.S).group(1))
        assert ld["@type"] == "Recipe"
        assert ld["name"] == "HelloFresh Beef & garlic rice bowl"
        assert ld["recipeIngredient"] == INGREDIENTS
        assert ld["recipeYield"] == "1 serving"
        assert ld["nutrition"]["calories"] == "641 calories"
        assert ld["nutrition"]["proteinContent"] == "36.9 g"
        assert ld["nutrition"]["sodiumContent"] == "1580 mg"
        assert client.get(f"{PUBLIC_URL}/food/forged.token").status_code == 404


def test_add_button_requires_password_then_creates_food():
    RecordingClient.specs.clear()
    url = FoodLinks(_auth(), client_factory=RecordingClient).make(_spec())
    with _client() as client:
        denied = client.post(f"{url}/add", data={"password": "nope"})
        assert denied.status_code == 401 and RecordingClient.specs == []
        ok = client.post(f"{url}/add", data={"password": PASSWORD})
        assert ok.status_code == 200
        assert "Added to MyFitnessPal" in ok.text and "food-9" in ok.text
        assert RecordingClient.specs[0].nutrition.calories == 641


def test_create_food_link_tool():
    import asyncio

    server = create_server(client_factory=RecordingClient, auth=_auth())
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert "create_food_link" in names
    result = asyncio.run(
        server.call_tool(
            "create_food_link",
            {"name": "Beef bowl", "brand": "HelloFresh", "ingredients": INGREDIENTS,
             "nutrition": {"energy_kj": 2680, "protein_g": 36.9}, "per_100g": {"energy_kj": 620}},
        )
    )
    out = json.loads(result.content[0].text)
    assert out["url"].startswith(f"{PUBLIC_URL}/food/")
    assert out["nutrition"]["serving_weight_g"] == 432
    assert out["ingredients"] == INGREDIENTS


def test_stdio_server_has_no_link_tool():
    import asyncio

    names = {t.name for t in asyncio.run(create_server(client_factory=RecordingClient).list_tools())}
    assert "create_food_link" not in names


def test_serving_line_shows_derived_weight():
    spec = _spec()
    assert spec.nutrition.serving_weight_g == 432
    page = render_food_page(spec, [], "http://localhost/food/x")
    assert "<p>Per 1 serving (432 g)</p>" in page


def test_serving_line_omits_weight_when_unknown():
    spec = _spec()
    spec.nutrition.serving_weight_g = None
    page = render_food_page(spec, [], "http://localhost/food/x")
    assert "<p>Per 1 serving</p>" in page


# -- recipe links --------------------------------------------------------------

RECIPE_INGREDIENTS = [
    "330 g chicken breast",
    "6 mini flour tortillas",
    "1 baby cos lettuce",
    "1 cucumber",
    "2 tbs hoisin sauce",
    "1/2 tbs soy sauce",
    "2 tbs garlic aioli",
    "1 drizzle olive oil",
]
METHOD = [
    "Slice the chicken into 1cm strips and fry over high heat until browned.",
    "Add the hoisin and soy with a splash of water; toss to glaze.",
    "Fill the tortillas with salad and chicken, then drizzle with aioli.",
]


def _recipe(**overrides):
    from connectors.myfitnesspal.links import RecipeSpec

    kwargs = dict(
        name="Hoisin chicken tacos",
        ingredients=RECIPE_INGREDIENTS,
        servings=2,
        instructions=METHOD,
        author="HelloFresh",
    )
    kwargs.update(overrides)
    return RecipeSpec(**kwargs)


def test_recipe_link_round_trips():
    links = FoodLinks(_auth(), client_factory=RecordingClient)
    url = links.make_recipe(_recipe())
    assert url.startswith(f"{PUBLIC_URL}/recipe/z")
    token = url.rsplit("/", 1)[1]
    spec = links.load_recipe(token)
    assert spec.name == "Hoisin chicken tacos"
    assert spec.ingredients == RECIPE_INGREDIENTS
    assert spec.instructions == METHOD
    assert spec.servings == 2 and spec.author == "HelloFresh" and spec.nutrition is None
    # A recipe token must not be usable as a food token, or vice versa.
    assert links.load(token) is None
    assert links.load_recipe(links.make(_spec()).rsplit("/", 1)[1]) is None
    assert FoodLinks(_auth("other"), client_factory=RecordingClient).load_recipe(token) is None


def test_recipe_link_stays_pasteable():
    """The whole recipe rides in the URL, so watch its size as fields are added."""
    links = FoodLinks(_auth(), client_factory=RecordingClient)
    assert len(links.make_recipe(_recipe(instructions=[]))) < 500
    assert len(links.make_recipe(_recipe())) < 900


def test_recipe_page_marks_ingredients_up_three_ways():
    url = FoodLinks(_auth(), client_factory=RecordingClient).make_recipe(_recipe())
    with _client() as client:
        r = client.get(url)
        assert r.status_code == 200
        ld = json.loads(re.search(r"<script type='application/ld\+json'>(.*?)</script>", r.text, re.S).group(1))
        assert ld["@type"] == "Recipe"
        assert ld["name"] == "Hoisin chicken tacos"
        assert ld["recipeIngredient"] == RECIPE_INGREDIENTS
        assert ld["recipeYield"] == "2 servings"
        assert ld["recipeInstructions"][0]["text"] == METHOD[0]
        assert "nutrition" not in ld
        # microdata and hRecipe, for scrapers that do not read JSON-LD
        assert "itemtype='https://schema.org/Recipe'" in r.text
        assert "<li class='ingredient' itemprop='recipeIngredient'>330 g chicken breast</li>" in r.text
        assert "class='fn' itemprop='name'" in r.text and "class='yield'" in r.text
        # the paste-it-yourself fallback
        assert "330 g chicken breast\n6 mini flour tortillas" in r.text
        assert client.get(f"{PUBLIC_URL}/recipe/forged.token").status_code == 404


def test_recipe_page_links_to_the_exact_food_when_nutrition_is_given():
    links = FoodLinks(_auth(), client_factory=RecordingClient)
    url = links.make_recipe(_recipe(nutrition=_spec().nutrition))
    with _client() as client:
        r = client.get(url)
        assert r.status_code == 200
        ld = json.loads(re.search(r"<script type='application/ld\+json'>(.*?)</script>", r.text, re.S).group(1))
        assert ld["nutrition"]["calories"] == "641 calories"
        food_url = re.search(r"href='(http://localhost/food/[^']+)'", r.text).group(1)
        spec, ingredients = links.load(food_url.rsplit("/", 1)[1])
        assert spec.nutrition.calories == 641 and spec.brand == "HelloFresh"
        assert ingredients == RECIPE_INGREDIENTS
        assert client.get(food_url).status_code == 200


def test_create_recipe_link_tool():
    import asyncio

    server = create_server(client_factory=RecordingClient, auth=_auth())
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert "create_recipe_link" in names
    assert "create_recipe_link" not in {
        t.name for t in asyncio.run(create_server(client_factory=RecordingClient).list_tools())
    }
    result = asyncio.run(
        server.call_tool(
            "create_recipe_link",
            {"name": "Hoisin chicken tacos", "ingredients": RECIPE_INGREDIENTS, "servings": 2,
             "nutrition": {"energy_kj": 2680, "protein_g": 36.9}, "per_100g": {"energy_kj": 620}},
        )
    )
    out = json.loads(result.content[0].text)
    assert out["url"].startswith(f"{PUBLIC_URL}/recipe/")
    assert out["servings"] == 2
    assert out["nutrition"]["serving_weight_g"] == 432


def test_page_titles_use_the_dish_name():
    from connectors.myfitnesspal.links import render_recipe_page

    assert "<title>Hoisin chicken tacos</title>" in render_recipe_page(_recipe(), "http://localhost/recipe/x")
    assert "<title>Beef &amp; garlic rice bowl</title>" in render_food_page(_spec(), [], "http://localhost/food/x")
