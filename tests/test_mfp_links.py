"""Tests for shareable food links and their phone page."""

import json
import re

from starlette.testclient import TestClient

from connectors.myfitnesspal.auth import PasswordAuthProvider
from connectors.myfitnesspal.links import FoodLinks
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
