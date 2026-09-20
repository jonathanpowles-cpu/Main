"""MCP server exposing the MyFitnessPal nutrient connector.

Run with ``python -m connectors.myfitnesspal serve`` (stdio transport) and
register it as a connector in Claude. The model reads the nutrition panel
from the photo itself and passes the values to these tools.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from .auth import SCOPE, PasswordAuthProvider
from .links import FoodLinks
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

If the user is on their phone or asks for a link, call create_food_link
instead (when available): it returns a page they can open on the phone to add
the food, or paste into the MyFitnessPal app's "Import from web". Pass the
recipe's ingredient lines too if they are visible.
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


def create_server(client_factory=MFPClient.from_env, auth: PasswordAuthProvider | None = None):
    """Build the MCP server.

    ``client_factory`` is injectable for tests. Pass ``auth`` to protect the
    HTTP transport with the password-guarded OAuth server (required for
    hosted use); stdio needs no auth.
    """
    from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
    from mcp.server.mcpserver import MCPServer
    from starlette.requests import Request
    from starlette.responses import JSONResponse, PlainTextResponse

    auth_kwargs: dict[str, Any] = {}
    if auth is not None:
        auth_kwargs = {
            "auth_server_provider": auth,
            "auth": AuthSettings(
                issuer_url=auth.public_url,
                resource_server_url=f"{auth.public_url}/mcp",
                client_registration_options=ClientRegistrationOptions(
                    enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]
                ),
                required_scopes=[SCOPE],
                validate_token_resource=False,
            ),
        }

    server = MCPServer(
        name="myfitnesspal-nutrients",
        title="MyFitnessPal Nutrient Connector",
        instructions=INSTRUCTIONS,
        version="0.1.0",
        **auth_kwargs,
    )

    @server.custom_route("/", methods=["GET"])
    async def index(_: Request) -> PlainTextResponse:
        return PlainTextResponse("MyFitnessPal nutrient connector. MCP endpoint: /mcp\n")

    @server.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    if auth is not None:
        server.custom_route("/login", methods=["GET"])(auth.login_page)
        server.custom_route("/login", methods=["POST"])(auth.login_submit)

        links = FoodLinks(auth, client_factory=client_factory)
        server.custom_route("/food/{token}", methods=["GET"])(links.food_page)
        server.custom_route("/food/{token}/add", methods=["POST"])(links.add_food)

        @server.tool()
        def create_food_link(
            name: str,
            nutrition: NutritionInput,
            brand: str | None = None,
            ingredients: list[str] | None = None,
            serving_description: str = "serving",
            per_100g: NutritionInput | None = None,
            country_code: str = "AU",
        ) -> dict[str, Any]:
            """Make a shareable link for this food. Opening it on a phone shows the nutrients with an "Add to MyFitnessPal" button, and the page can be pasted into the MyFitnessPal app's Recipes > Import from web. Creates nothing until the user acts."""
            spec = build_spec(name, nutrition, brand, serving_description, per_100g, country_code)
            url = links.make(spec, ingredients)
            return {"url": url, "nutrition": spec.nutrition.to_dict(), "ingredients": ingredients or []}

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


def run_http(server, public_url: str, host: str = "0.0.0.0", port: int = 8000) -> None:
    """Serve over Streamable HTTP, accepting only requests addressed to ``public_url``."""
    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    public_host = urlparse(public_url).netloc
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[public_host, f"{public_host}:*", "localhost:*", "127.0.0.1:*"],
        allowed_origins=[public_url.rstrip("/"), "http://localhost:*", "http://127.0.0.1:*"],
    )
    app = server.streamable_http_app(host=host, transport_security=security)
    uvicorn.run(app, host=host, port=port, log_level="info")


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
