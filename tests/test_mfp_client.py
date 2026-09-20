"""Tests for the MyFitnessPal payload builder and client (HTTP mocked)."""

import json

import pytest
import requests

from connectors.myfitnesspal.mfp_client import (
    FoodSpec,
    MFPAuthError,
    MFPClient,
    MFPError,
    build_food_payload,
    cookies_from_file,
    cookies_from_header,
    manual_entry,
)
from connectors.myfitnesspal.nutrition import NutritionFacts


def _spec(**overrides) -> FoodSpec:
    facts = NutritionFacts(
        calories=641,
        protein_g=36.9,
        fat_g=22.2,
        saturated_fat_g=9.4,
        carbohydrates_g=70.7,
        sugars_g=9,
        sodium_mg=1580,
        fibre_g=8.5,
        energy_kj=2680,
        serving_weight_g=432,
    )
    kwargs = dict(name="Beef & garlic rice bowl", nutrition=facts, brand="HelloFresh")
    kwargs.update(overrides)
    return FoodSpec(**kwargs)


def test_build_food_payload_maps_nutrients_to_mfp_keys():
    item = build_food_payload(_spec())["item"]
    assert item["description"] == "Beef & garlic rice bowl"
    assert item["brand_name"] == "HelloFresh"
    assert item["public"] is False
    assert item["nutritional_contents"] == {
        "energy": {"unit": "calories", "value": 641},
        "protein": 36.9,
        "fat": 22.2,
        "saturated_fat": 9.4,
        "sodium": 1580,
        "carbohydrates": 70.7,
        "fiber": 8.5,
        "sugar": 9,
    }


def test_build_food_payload_serving_sizes_include_gram_serving():
    sizes = build_food_payload(_spec())["item"]["serving_sizes"]
    assert sizes[0] == {"index": 0, "value": 1, "unit": "serving", "nutrition_multiplier": 1.0}
    assert sizes[1]["unit"] == "g"
    assert sizes[1]["nutrition_multiplier"] == pytest.approx(1 / 432, rel=1e-3)


def test_build_food_payload_without_weight_has_single_serving():
    spec = _spec()
    spec.nutrition.serving_weight_g = None
    assert len(build_food_payload(spec)["item"]["serving_sizes"]) == 1


def test_build_food_payload_rejects_empty_name():
    with pytest.raises(ValueError):
        build_food_payload(_spec(name="  "))


def test_manual_entry_follows_form_order():
    fields = [row["field"] for row in manual_entry(_spec())]
    assert fields[:3] == ["Brand", "Description", "Serving Size"]
    assert fields[3] == "Calories"
    assert fields[-1] == "Protein (g)"
    assert "Trans Fat (g)" not in fields


def test_cookies_from_header():
    assert cookies_from_header("a=1; b=x=y ;c=3") == {"a": "1", "b": "x=y", "c": "3"}


def test_cookies_from_file_filters_to_myfitnesspal(tmp_path):
    path = tmp_path / "cookies.txt"
    path.write_text(
        "# Netscape HTTP Cookie File\n"
        ".myfitnesspal.com\tTRUE\t/\tTRUE\t0\t_session\tabc\n"
        ".example.com\tTRUE\t/\tTRUE\t0\tother\tzzz\n"
    )
    assert cookies_from_file(path) == {"_session": "abc"}


# --- client with a fake HTTP session -------------------------------------


class FakeResponse:
    def __init__(self, status_code=200, body=None, content_type="application/json", text=None):
        self.status_code = status_code
        self._body = body
        self.headers = {"Content-Type": content_type}
        self.text = text if text is not None else json.dumps(body or {})

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession(requests.Session):
    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)


AUTH_OK = {"access_token": "tok123", "token_type": "Bearer", "user_id": "u42"}


def test_create_food_authenticates_then_posts():
    session = FakeSession([
        FakeResponse(200, AUTH_OK),
        FakeResponse(200, {"item": {"id": "food-1", "description": "Beef & garlic rice bowl"}}),
    ])
    client = MFPClient(cookies={"_session": "abc"}, session=session)
    result = client.create_food(_spec())

    assert result["id"] == "food-1"
    method, url, kwargs = session.calls[0]
    assert (method, url) == ("GET", "https://www.myfitnesspal.com/user/auth_token")
    assert kwargs["params"] == {"refresh": "true"}

    method, url, kwargs = session.calls[1]
    assert (method, url) == ("POST", "https://api.myfitnesspal.com/v2/foods")
    assert kwargs["headers"]["Authorization"] == "Bearer tok123"
    assert kwargs["headers"]["mfp-user-id"] == "u42"
    assert kwargs["headers"]["mfp-client-id"] == "mfp-main-js"
    assert json.loads(kwargs["data"]) == build_food_payload(_spec())


def test_html_auth_response_raises_auth_error():
    session = FakeSession([FakeResponse(200, None, content_type="text/html", text="<html>login</html>")])
    with pytest.raises(MFPAuthError):
        MFPClient(cookies={}, session=session).authenticate()


def test_api_error_is_reported():
    session = FakeSession([FakeResponse(200, AUTH_OK), FakeResponse(422, {"errors": ["bad"]})])
    with pytest.raises(MFPError, match="422"):
        MFPClient(cookies={}, session=session).create_food(_spec())


def test_preview_sends_nothing():
    session = FakeSession([])
    preview = MFPClient(cookies={}, session=session).preview(_spec())
    assert session.calls == []
    assert preview["payload"] == build_food_payload(_spec())
    assert preview["endpoint"].endswith("/v2/foods")
