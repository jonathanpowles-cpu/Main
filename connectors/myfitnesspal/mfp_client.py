"""Minimal MyFitnessPal client for creating custom foods.

MyFitnessPal has no public API. This client talks to the same private
endpoints the MyFitnessPal website uses, authenticated with the cookies of a
logged-in browser session:

1. ``GET https://www.myfitnesspal.com/user/auth_token?refresh=true`` exchanges
   the session cookie for a short-lived bearer token and user id.
2. ``POST https://api.myfitnesspal.com/v2/foods`` creates the food.

These endpoints are unofficial and may change without notice; every request
shape is a single function here so it is easy to adjust. Use
:meth:`MFPClient.preview` (or ``--dry-run``) to see the exact payload without
sending anything.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any

import requests

from .nutrition import NutritionFacts

WEB_BASE_URL = "https://www.myfitnesspal.com"
API_BASE_URL = "https://api.myfitnesspal.com/v2"
CLIENT_ID = "mfp-main-js"
USER_AGENT = "Mozilla/5.0 (compatible; mfp-nutrient-connector/0.1)"

# NutritionFacts field -> MyFitnessPal nutritional_contents key
MFP_NUTRIENT_KEYS: dict[str, str] = {
    "protein_g": "protein",
    "fat_g": "fat",
    "saturated_fat_g": "saturated_fat",
    "trans_fat_g": "trans_fat",
    "polyunsaturated_fat_g": "polyunsaturated_fat",
    "monounsaturated_fat_g": "monounsaturated_fat",
    "cholesterol_mg": "cholesterol",
    "sodium_mg": "sodium",
    "potassium_mg": "potassium",
    "carbohydrates_g": "carbohydrates",
    "fibre_g": "fiber",
    "sugars_g": "sugar",
}

# Field order and labels of MyFitnessPal's "Create a Food" web form, for the
# manual-entry fallback.
MANUAL_ENTRY_FIELDS: list[tuple[str, str]] = [
    ("calories", "Calories"),
    ("fat_g", "Total Fat (g)"),
    ("saturated_fat_g", "Saturated Fat (g)"),
    ("polyunsaturated_fat_g", "Polyunsaturated Fat (g)"),
    ("monounsaturated_fat_g", "Monounsaturated Fat (g)"),
    ("trans_fat_g", "Trans Fat (g)"),
    ("cholesterol_mg", "Cholesterol (mg)"),
    ("sodium_mg", "Sodium (mg)"),
    ("potassium_mg", "Potassium (mg)"),
    ("carbohydrates_g", "Total Carbohydrates (g)"),
    ("fibre_g", "Dietary Fiber (g)"),
    ("sugars_g", "Sugars (g)"),
    ("protein_g", "Protein (g)"),
]


class MFPError(Exception):
    """A MyFitnessPal request failed."""


class MFPAuthError(MFPError):
    """The session cookies were missing, expired or rejected."""


@dataclass
class FoodSpec:
    """Everything needed to create one custom food."""

    name: str
    nutrition: NutritionFacts
    brand: str | None = None
    serving_description: str = "serving"
    serving_quantity: float = 1.0
    country_code: str = "AU"
    public: bool = False
    extra_serving_sizes: list[dict[str, Any]] = field(default_factory=list)


def _clean_number(value: float) -> float | int:
    rounded = round(float(value), 2)
    return int(rounded) if rounded == int(rounded) else rounded


def nutritional_contents(facts: NutritionFacts) -> dict[str, Any]:
    """Map :class:`NutritionFacts` to MyFitnessPal's ``nutritional_contents`` object."""
    contents: dict[str, Any] = {"energy": {"unit": "calories", "value": _clean_number(facts.calories)}}
    for field_name, mfp_key in MFP_NUTRIENT_KEYS.items():
        value = getattr(facts, field_name)
        if value is not None:
            contents[mfp_key] = _clean_number(value)
    return contents


def serving_sizes(spec: FoodSpec) -> list[dict[str, Any]]:
    """Serving sizes for the food.

    The first entry is the label's serving (multiplier 1). If the serving
    weight is known, a "1 g" serving is added so the food can be logged by
    weight as well.
    """
    sizes: list[dict[str, Any]] = [
        {
            "index": 0,
            "value": _clean_number(spec.serving_quantity),
            "unit": spec.serving_description,
            "nutrition_multiplier": 1.0,
        }
    ]
    weight = spec.nutrition.serving_weight_g
    if weight:
        sizes.append(
            {
                "index": 1,
                "value": 1,
                "unit": "g",
                "nutrition_multiplier": round(1.0 / weight, 6),
            }
        )
    for extra in spec.extra_serving_sizes:
        sizes.append({"index": len(sizes), **extra})
    return sizes


def build_food_payload(spec: FoodSpec) -> dict[str, Any]:
    """Build the JSON body for ``POST /v2/foods``."""
    if not spec.name.strip():
        raise ValueError("Food name must not be empty")
    if spec.nutrition.calories < 0:
        raise ValueError("Calories must not be negative")
    item: dict[str, Any] = {
        "type": "food",
        "description": spec.name.strip(),
        "brand_name": (spec.brand or "").strip(),
        "public": bool(spec.public),
        "verified": False,
        "country_code": spec.country_code,
        "nutritional_contents": nutritional_contents(spec.nutrition),
        "serving_sizes": serving_sizes(spec),
    }
    return {"item": item}


def manual_entry(spec: FoodSpec) -> list[dict[str, Any]]:
    """The values to type into MyFitnessPal's "Create a Food" form, in form order."""
    rows: list[dict[str, Any]] = [
        {"field": "Brand", "value": spec.brand or ""},
        {"field": "Description", "value": spec.name},
        {
            "field": "Serving Size",
            "value": f"{_clean_number(spec.serving_quantity)} {spec.serving_description}",
        },
    ]
    for field_name, label in MANUAL_ENTRY_FIELDS:
        value = getattr(spec.nutrition, field_name)
        if value is not None:
            rows.append({"field": label, "value": _clean_number(value)})
    return rows


# --------------------------------------------------------------------------
# Cookie loading
# --------------------------------------------------------------------------


def cookies_from_header(header: str) -> dict[str, str]:
    """Parse a ``Cookie:`` header value (``a=1; b=2``) into a dict."""
    cookies: dict[str, str] = {}
    for part in header.split(";"):
        if "=" in part:
            name, value = part.split("=", 1)
            cookies[name.strip()] = value.strip()
    return cookies


def cookies_from_file(path: str | Path) -> dict[str, str]:
    """Load cookies from a Netscape ``cookies.txt`` export."""
    jar = MozillaCookieJar(str(path))
    jar.load(ignore_discard=True, ignore_expires=True)
    return {c.name: c.value for c in jar if "myfitnesspal" in (c.domain or "")}


def cookies_from_env() -> dict[str, str]:
    """Read cookies from ``MFP_COOKIE_HEADER`` or ``MFP_COOKIES_FILE``."""
    header = os.environ.get("MFP_COOKIE_HEADER")
    if header:
        return cookies_from_header(header)
    path = os.environ.get("MFP_COOKIES_FILE")
    if path:
        return cookies_from_file(path)
    raise MFPAuthError(
        "No MyFitnessPal cookies configured. Set MFP_COOKIE_HEADER to the Cookie "
        "header of a logged-in myfitnesspal.com session, or MFP_COOKIES_FILE to a "
        "Netscape cookies.txt export."
    )


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------


class MFPClient:
    def __init__(
        self,
        cookies: dict[str, str] | None = None,
        session: requests.Session | None = None,
        web_base_url: str = WEB_BASE_URL,
        api_base_url: str = API_BASE_URL,
        client_id: str = CLIENT_ID,
        timeout: float = 30.0,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        for name, value in (cookies or {}).items():
            self.session.cookies.set(name, value, domain=".myfitnesspal.com")
        self.web_base_url = web_base_url.rstrip("/")
        self.api_base_url = api_base_url.rstrip("/")
        self.client_id = client_id
        self.timeout = timeout
        self._token: str | None = None
        self._user_id: str | None = None

    @classmethod
    def from_env(cls, **kwargs: Any) -> "MFPClient":
        return cls(cookies=cookies_from_env(), **kwargs)

    # -- auth ---------------------------------------------------------------

    def authenticate(self) -> tuple[str, str]:
        """Exchange the session cookie for a bearer token; returns (token, user_id)."""
        response = self.session.get(
            f"{self.web_base_url}/user/auth_token",
            params={"refresh": "true"},
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        if response.status_code in (401, 403) or "text/html" in response.headers.get("Content-Type", ""):
            raise MFPAuthError(
                "MyFitnessPal rejected the session cookies (are they expired? "
                "log in again in the browser and re-export them)."
            )
        if response.status_code != 200:
            raise MFPError(f"auth_token returned HTTP {response.status_code}: {response.text[:200]}")
        try:
            data = response.json()
        except ValueError as exc:
            raise MFPAuthError("auth_token did not return JSON; session cookies are probably invalid") from exc
        token, user_id = data.get("access_token"), data.get("user_id")
        if not token or not user_id:
            raise MFPAuthError(f"auth_token response missing access_token/user_id: {data}")
        self._token, self._user_id = str(token), str(user_id)
        return self._token, self._user_id

    def _api_headers(self) -> dict[str, str]:
        if self._token is None:
            self.authenticate()
        return {
            "Authorization": f"Bearer {self._token}",
            "mfp-client-id": self.client_id,
            "mfp-user-id": self._user_id or "",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # -- foods ----------------------------------------------------------------

    def preview(self, spec: FoodSpec) -> dict[str, Any]:
        """Return what :meth:`create_food` would send, without sending it."""
        return {
            "endpoint": f"POST {self.api_base_url}/foods",
            "payload": build_food_payload(spec),
            "manual_entry": manual_entry(spec),
        }

    def create_food(self, spec: FoodSpec) -> dict[str, Any]:
        """Create a custom food in the authenticated user's account.

        Returns the created item as MyFitnessPal reports it (with its ``id``).
        """
        payload = build_food_payload(spec)
        response = self.session.post(
            f"{self.api_base_url}/foods",
            data=json.dumps(payload),
            headers=self._api_headers(),
            timeout=self.timeout,
        )
        if response.status_code == 401:
            raise MFPAuthError("MyFitnessPal API rejected the bearer token (HTTP 401)")
        if response.status_code >= 400:
            raise MFPError(f"Create food failed: HTTP {response.status_code}: {response.text[:500]}")
        try:
            body = response.json()
        except ValueError:
            body = {}
        item = body.get("item", body) if isinstance(body, dict) else body
        return {
            "id": item.get("id") if isinstance(item, dict) else None,
            "description": spec.name,
            "brand": spec.brand,
            "item": item,
        }
