"""Command-line interface for the MyFitnessPal nutrient connector.

Examples::

    # Parse a label pasted into a file and print the nutrients
    python -m connectors.myfitnesspal parse label.txt

    # Preview the food that would be created (no network)
    python -m connectors.myfitnesspal create --name "Beef & garlic rice" \
        --brand HelloFresh --label label.txt --dry-run

    # Create it for real (needs MFP_COOKIE_HEADER or MFP_COOKIES_FILE)
    python -m connectors.myfitnesspal create --name "Beef & garlic rice" \
        --brand HelloFresh --kj 2680 --protein 36.9 --fat 22.2 --saturated 9.4 \
        --carbs 70.7 --sugars 9 --sodium 1580 --fibre 8.5

    # Run as an MCP server over stdio (Claude Desktop / Claude Code)
    python -m connectors.myfitnesspal serve

    # Run as a hosted HTTPS connector for claude.ai (needs CONNECTOR_PASSWORD,
    # PUBLIC_URL and the MFP cookie variables in the environment)
    python -m connectors.myfitnesspal serve --transport http --port 8000
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .mfp_client import FoodSpec, MFPClient, MFPError
from .nutrition import NutritionFacts, kj_to_kcal, parse_label

_NUTRIENT_ARGS: list[tuple[str, str, str]] = [
    ("--protein", "protein_g", "Protein (g)"),
    ("--fat", "fat_g", "Total fat (g)"),
    ("--saturated", "saturated_fat_g", "Saturated fat (g)"),
    ("--trans", "trans_fat_g", "Trans fat (g)"),
    ("--poly", "polyunsaturated_fat_g", "Polyunsaturated fat (g)"),
    ("--mono", "monounsaturated_fat_g", "Monounsaturated fat (g)"),
    ("--cholesterol", "cholesterol_mg", "Cholesterol (mg)"),
    ("--sodium", "sodium_mg", "Sodium (mg)"),
    ("--potassium", "potassium_mg", "Potassium (mg)"),
    ("--carbs", "carbohydrates_g", "Carbohydrate (g)"),
    ("--fibre", "fibre_g", "Dietary fibre (g)"),
    ("--sugars", "sugars_g", "Sugars (g)"),
    ("--serving-weight", "serving_weight_g", "Serving weight (g)"),
]


def _read_text(path: str) -> str:
    return sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()


def _facts_from_args(args: argparse.Namespace) -> NutritionFacts:
    if args.label:
        return parse_label(_read_text(args.label)).per_serving
    if args.calories is None and args.kj is None:
        raise SystemExit("error: give --label, or --calories / --kj plus nutrient flags")
    nutrients = {dest: getattr(args, dest) for _, dest, _ in _NUTRIENT_ARGS if getattr(args, dest) is not None}
    calories = args.calories if args.calories is not None else kj_to_kcal(args.kj)
    return NutritionFacts(calories=calories, energy_kj=args.kj, **nutrients)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m connectors.myfitnesspal", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="parse nutrition panel text and print JSON")
    p_parse.add_argument("label", help="path to a text file, or - for stdin")

    p_create = sub.add_parser("create", help="create (or preview) a food in MyFitnessPal")
    p_create.add_argument("--name", required=True, help="food description, e.g. 'Beef & garlic rice bowl'")
    p_create.add_argument("--brand", default=None, help="brand, e.g. HelloFresh")
    p_create.add_argument("--serving", default="serving", help="serving unit label (default: serving)")
    p_create.add_argument("--country", default="AU", help="country code (default: AU)")
    p_create.add_argument("--label", help="nutrition panel text file (or - for stdin)")
    p_create.add_argument("--calories", type=float, help="energy per serving (kcal)")
    p_create.add_argument("--kj", type=float, help="energy per serving (kJ)")
    for flag, dest, help_text in _NUTRIENT_ARGS:
        p_create.add_argument(flag, dest=dest, type=float, default=None, help=help_text)
    p_create.add_argument("--dry-run", action="store_true", help="print the payload instead of sending it")
    p_create.add_argument(
        "--link",
        action="store_true",
        help="print a shareable food link for the hosted service instead of creating the food "
        "(needs PUBLIC_URL and CONNECTOR_PASSWORD / CONNECTOR_SECRET)",
    )
    p_create.add_argument("--ingredient", action="append", default=[], help="ingredient line for the link page (repeatable)")

    p_serve = sub.add_parser("serve", help="run the MCP server")
    p_serve.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    p_serve.add_argument("--host", default="0.0.0.0", help="bind address for http (default: 0.0.0.0)")
    p_serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")), help="port for http (default: $PORT or 8000)")
    p_serve.add_argument(
        "--public-url",
        default=os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL"),
        help="public https URL of this server (default: $PUBLIC_URL or $RENDER_EXTERNAL_URL)",
    )
    return parser


def _serve(args: argparse.Namespace) -> int:
    from .server import create_server, run_http

    if args.transport == "stdio":
        create_server().run(transport="stdio")
        return 0

    from .auth import PasswordAuthProvider

    password = os.environ.get("CONNECTOR_PASSWORD")
    if not password:
        print("error: CONNECTOR_PASSWORD must be set to serve over http (it protects your MFP cookies)", file=sys.stderr)
        return 2
    if not args.public_url:
        print("error: --public-url (or $PUBLIC_URL) is required to serve over http", file=sys.stderr)
        return 2
    auth = PasswordAuthProvider(password, args.public_url, secret=os.environ.get("CONNECTOR_SECRET"))
    run_http(create_server(auth=auth), public_url=args.public_url, host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "serve":
        return _serve(args)

    if args.command == "parse":
        print(json.dumps(parse_label(_read_text(args.label)).to_dict(), indent=2))
        return 0

    spec = FoodSpec(
        name=args.name,
        nutrition=_facts_from_args(args),
        brand=args.brand,
        serving_description=args.serving,
        country_code=args.country,
    )
    if args.dry_run:
        print(json.dumps(MFPClient(cookies={}).preview(spec), indent=2))
        return 0
    if args.link:
        from .auth import PasswordAuthProvider
        from .links import FoodLinks

        public_url = os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL")
        password = os.environ.get("CONNECTOR_PASSWORD")
        if not public_url or not password:
            print("error: --link needs PUBLIC_URL and CONNECTOR_PASSWORD in the environment", file=sys.stderr)
            return 2
        auth = PasswordAuthProvider(password, public_url, secret=os.environ.get("CONNECTOR_SECRET"))
        print(FoodLinks(auth).make(spec, args.ingredient))
        return 0
    try:
        result = MFPClient.from_env().create_food(spec)
    except MFPError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
