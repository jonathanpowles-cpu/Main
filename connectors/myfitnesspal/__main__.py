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

    # Run as an MCP server over stdio
    python -m connectors.myfitnesspal serve
"""

from __future__ import annotations

import argparse
import json
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

    sub.add_parser("serve", help="run the MCP server on stdio")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "serve":
        from .server import main as serve

        serve()
        return 0

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
    try:
        result = MFPClient.from_env().create_food(spec)
    except MFPError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
