"""MCP server exposing the MyFitnessPal nutrient connector.

Run with ``python -m connectors.myfitnesspal serve`` (stdio transport) and
register it as a connector in Claude. The model reads the nutrition panel
from the photo itself and passes the values to these tools.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from .mfp_client import FoodSpec, MFPClient
from .nutrition import NutritionFacts, derive_serving_weight_g, kj_to_kcal, parse_label

INSTRUCTIONS = """\
Creates custom foods in the user's MyFitnessPal account from a nutrition
information panel (recipe card, packet label, meal-kit sheet).

Workflow:
1. Read the nutrients off the image or text the user gave you. Use the
   "per serving" column. Never guess or fill in values that are not on the
   label; leave them out instead.
2. Call preview_food and show the user the name, brand and nutrients you are
   about to create. Ask them to confirm.
3. Call create_food with the same arguments once they confirm.

If the label has a "per 100 g" column, pass it as per_100g so the serving
weight can be derived and the food can also be logged by weight.
"""


class NutritionInput(BaseModel):
    """Nutrients for ONE serving as printed on the label. Give either calories or energy_kj."""

    calories: float | None = Field(None, description="Energy per serving in kcal (labelled Cal/kcal)")
    energy_kj: float | None = Field(None, description="Energy per serving in kJ")
    protein_g: float | None = None
    fat_g: float | None = Field(None, description="Total fat, grams")
    saturated_fat_g: float | None = None
    trans_fat_g: float | None = None
    polyunsaturated_fat_g: float | None = None
    monounsaturated_fat_g: float | None = None
    cholesterol_mg: float | None = None
    sodium_mg: float | None = Field(None, description="Sodium in milligrams (not salt)")
    potassium_mg: float | None = None
    carbohydrates_g: float | None = Field(None, description="Total carbohydrate, grams")
    fibre_g: float | None = Field(None, description="Dietary fibre, grams")
    sugars_g: float | None = None
    serving_weight_g: float | None = Field(None, description="Weight of one serving in grams, if printed")

    @model_validator(mode="after")
    def _needs_energy(self) -> "NutritionInput":
        if self.calories is None and self.energy_kj is None:
            raise ValueError("Provide calories or energy_kj")
        return self

    def to_facts(self) -> NutritionFacts:
        data = self.model_dump()
        if data["calories"] is None:
            data["calories"] = kj_to_kcal(data["energy_kj"])
        return NutritionFacts(**data)


def build_spec(
    name: str,
    nutrition: NutritionInput,
    brand: str | None,
    serving_description: str,
    per_100g: NutritionInput | None,
    country_code: str,
) -> FoodSpec:
    facts = nutrition.to_facts()
    if per_100g is not None and facts.serving_weight_g is None:
        facts.serving_weight_g = derive_serving_weight_g(facts, per_100g.to_facts())
    return FoodSpec(
        name=name,
        nutrition=facts,
        brand=brand,
        serving_description=serving_description,
        country_code=country_code,
    )


def create_server(client_factory=MFPClient.from_env):
    """Build the MCP server. ``client_factory`` is injectable for tests."""
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(
        name="myfitnesspal-nutrients",
        title="MyFitnessPal Nutrient Connector",
        instructions=INSTRUCTIONS,
        version="0.1.0",
    )

    @server.tool()
    def parse_nutrition_label(label_text: str) -> dict[str, Any]:
        """Parse the text of a nutrition panel (rows like 'Protein (g) 36.9g 8.5g') into structured per-serving and per-100g nutrients."""
        return parse_label(label_text).to_dict()

    @server.tool()
    def preview_food(
        name: str,
        nutrition: NutritionInput,
        brand: str | None = None,
        serving_description: str = "serving",
        per_100g: NutritionInput | None = None,
        country_code: str = "AU",
    ) -> dict[str, Any]:
        """Show exactly what create_food would send to MyFitnessPal, plus the values for manual entry. Sends nothing."""
        spec = build_spec(name, nutrition, brand, serving_description, per_100g, country_code)
        preview = MFPClient(cookies={}).preview(spec)
        preview["nutrition"] = spec.nutrition.to_dict()
        return preview

    @server.tool()
    def create_food(
        name: str,
        nutrition: NutritionInput,
        brand: str | None = None,
        serving_description: str = "serving",
        per_100g: NutritionInput | None = None,
        country_code: str = "AU",
    ) -> dict[str, Any]:
        """Create a private custom food in the user's MyFitnessPal account. Call preview_food and get the user's confirmation first."""
        spec = build_spec(name, nutrition, brand, serving_description, per_100g, country_code)
        return client_factory().create_food(spec)

    @server.tool()
    def create_food_from_label(
        name: str,
        label_text: str,
        brand: str | None = None,
        serving_description: str = "serving",
        country_code: str = "AU",
    ) -> dict[str, Any]:
        """Parse nutrition panel text and create the food in MyFitnessPal in one step."""
        parsed = parse_label(label_text)
        spec = FoodSpec(
            name=name,
            nutrition=parsed.per_serving,
            brand=brand,
            serving_description=serving_description,
            country_code=country_code,
        )
        return client_factory().create_food(spec)

    return server


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
