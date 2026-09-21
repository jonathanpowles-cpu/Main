"""Tests for the MCP server tools (no network)."""

import asyncio
import json

import pytest

from connectors.myfitnesspal.server import create_server

NUTRITION = {
    "energy_kj": 2680,
    "calories": 641,
    "protein_g": 36.9,
    "fat_g": 22.2,
    "saturated_fat_g": 9.4,
    "carbohydrates_g": 70.7,
    "sugars_g": 9,
    "sodium_mg": 1580,
    "fibre_g": 8.5,
}


class RecordingClient:
    def __init__(self):
        self.specs = []

    def create_food(self, spec):
        self.specs.append(spec)
        return {"id": "food-1", "description": spec.name, "brand": spec.brand, "item": {}}


def _call(server, tool, args):
    result = asyncio.run(server.call_tool(tool, args))
    return json.loads(result.content[0].text)


def test_lists_expected_tools():
    server = create_server(client_factory=RecordingClient)
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"parse_nutrition_label", "preview_food", "create_food", "create_food_from_label"}


def test_preview_food_derives_serving_weight_from_per_100g():
    server = create_server(client_factory=RecordingClient)
    out = _call(
        server,
        "preview_food",
        {"name": "Beef bowl", "brand": "HelloFresh", "nutrition": NUTRITION, "per_100g": {"energy_kj": 620}},
    )
    assert out["nutrition"]["serving_weight_g"] == 432
    assert out["payload"]["item"]["nutritional_contents"]["energy"]["value"] == 641
    assert len(out["payload"]["item"]["serving_sizes"]) == 2


def test_create_food_uses_client():
    client = RecordingClient()
    server = create_server(client_factory=lambda: client)
    out = _call(server, "create_food", {"name": "Beef bowl", "nutrition": NUTRITION})
    assert out["id"] == "food-1"
    assert client.specs[0].nutrition.sodium_mg == 1580


def test_nutrition_requires_energy():
    server = create_server(client_factory=RecordingClient)
    with pytest.raises(Exception, match="calories or energy_kj"):
        _call(server, "preview_food", {"name": "x", "nutrition": {"protein_g": 1}})


def test_create_food_from_label_text():
    client = RecordingClient()
    server = create_server(client_factory=lambda: client)
    out = _call(
        server,
        "create_food_from_label",
        {"name": "Beef bowl", "label_text": "Energy 2680kJ (641Cal) 620kJ\nProtein 36.9g 8.5g"},
    )
    assert out["id"] == "food-1"
    assert client.specs[0].nutrition.protein_g == 36.9
    assert client.specs[0].nutrition.serving_weight_g == 432
