"""MyFitnessPal nutrient connector.

Turns a nutrition information panel (e.g. a HelloFresh recipe card) into a
custom food in MyFitnessPal. See README.md in this directory.
"""

from .nutrition import NutritionFacts, ParsedLabel, parse_label
from .mfp_client import FoodSpec, MFPClient, MFPAuthError, MFPError, build_food_payload

__all__ = [
    "NutritionFacts",
    "ParsedLabel",
    "parse_label",
    "FoodSpec",
    "MFPClient",
    "MFPAuthError",
    "MFPError",
    "build_food_payload",
]
