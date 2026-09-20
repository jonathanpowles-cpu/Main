"""Nutrition facts model, unit handling and nutrition-panel text parsing.

MyFitnessPal stores energy in kcal, macronutrients in grams and sodium /
potassium / cholesterol in milligrams. Australian and European labels usually
give energy in kJ (sometimes with kcal alongside) and list values both
"per serving" and "per 100 g". This module normalises all of that into a
single :class:`NutritionFacts` per serving.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields

KJ_PER_KCAL = 4.184

# Fields whose natural MFP unit is milligrams; everything else is grams.
_MG_FIELDS = {"sodium_mg", "potassium_mg", "cholesterol_mg"}


@dataclass
class NutritionFacts:
    """Nutrients for one serving of a food, in MyFitnessPal's units."""

    calories: float
    protein_g: float | None = None
    fat_g: float | None = None
    saturated_fat_g: float | None = None
    trans_fat_g: float | None = None
    polyunsaturated_fat_g: float | None = None
    monounsaturated_fat_g: float | None = None
    cholesterol_mg: float | None = None
    sodium_mg: float | None = None
    potassium_mg: float | None = None
    carbohydrates_g: float | None = None
    fibre_g: float | None = None
    sugars_g: float | None = None
    energy_kj: float | None = None
    serving_weight_g: float | None = None

    @classmethod
    def from_kilojoules(cls, energy_kj: float, **nutrients: float | None) -> "NutritionFacts":
        """Build facts from an energy value in kJ, deriving kcal."""
        return cls(calories=kj_to_kcal(energy_kj), energy_kj=energy_kj, **nutrients)

    def nutrient_items(self) -> dict[str, float]:
        """Nutrient values that are set, excluding energy_kj and serving weight."""
        skip = {"energy_kj", "serving_weight_g"}
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name not in skip and getattr(self, f.name) is not None
        }

    def to_dict(self) -> dict[str, float | None]:
        return asdict(self)


@dataclass
class ParsedLabel:
    """Result of parsing a nutrition panel: per-serving facts plus optional per-100 g facts."""

    per_serving: NutritionFacts
    per_100g: NutritionFacts | None = None

    def to_dict(self) -> dict:
        return {
            "per_serving": self.per_serving.to_dict(),
            "per_100g": self.per_100g.to_dict() if self.per_100g else None,
        }


def kj_to_kcal(kj: float) -> float:
    return round(kj / KJ_PER_KCAL, 1)


def derive_serving_weight_g(per_serving: NutritionFacts, per_100g: NutritionFacts) -> float | None:
    """Infer the serving weight from the ratio of per-serving to per-100 g values.

    Energy is used first (largest numbers, least rounding error), then the
    other nutrients in turn.
    """
    pairs: list[tuple[float | None, float | None]] = [
        (per_serving.energy_kj, per_100g.energy_kj),
        (per_serving.calories, per_100g.calories),
    ]
    for name, value in per_serving.nutrient_items().items():
        pairs.append((value, getattr(per_100g, name)))
    for serving_value, hundred_value in pairs:
        if serving_value and hundred_value:
            return round(100.0 * serving_value / hundred_value)
    return None


# --------------------------------------------------------------------------
# Label text parsing
# --------------------------------------------------------------------------

# Row label keywords -> NutritionFacts field. Order matters: more specific
# entries must come before generic ones ("saturated" before "fat").
_ROW_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(energy|calories|kilojoules|kcal)\b", re.I), "energy"),
    (re.compile(r"\bprotein\b", re.I), "protein_g"),
    (re.compile(r"\bsaturated\b", re.I), "saturated_fat_g"),
    (re.compile(r"\btrans\b", re.I), "trans_fat_g"),
    (re.compile(r"\bpolyunsaturated\b", re.I), "polyunsaturated_fat_g"),
    (re.compile(r"\bmonounsaturated\b", re.I), "monounsaturated_fat_g"),
    (re.compile(r"\bfat\b", re.I), "fat_g"),
    (re.compile(r"\bcholesterol\b", re.I), "cholesterol_mg"),
    (re.compile(r"\bsodium\b|\bsalt\b", re.I), "sodium_mg"),
    (re.compile(r"\bpotassium\b", re.I), "potassium_mg"),
    (re.compile(r"\b(carbohydrates?|carbs)\b", re.I), "carbohydrates_g"),
    (re.compile(r"\b(fibre|fiber)\b", re.I), "fibre_g"),
    (re.compile(r"\bsugars?\b", re.I), "sugars_g"),
]

_NUMBER_WITH_UNIT = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>kj|kcal|calories|cal|mcg|µg|mg|g)?(?![a-z])",
    re.I,
)
_UNIT_HINT = re.compile(r"\((?:kj|kcal|cal|g|mg|mcg|µg)\)", re.I)
_LEADING_DASH = re.compile(r"^[\s\-–—•·]+")


def _split_label_and_values(line: str) -> tuple[str, str]:
    """Return (label text, remainder containing the numeric columns)."""
    cleaned = _UNIT_HINT.sub(" ", _LEADING_DASH.sub("", line))
    match = re.search(r"\d", cleaned)
    if not match:
        return cleaned.strip(), ""
    return cleaned[: match.start()].strip(), cleaned[match.start():]


def _numbers(text: str) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for m in _NUMBER_WITH_UNIT.finditer(text):
        value = float(m.group("value").replace(",", "."))
        unit = (m.group("unit") or "").lower()
        out.append((value, unit))
    return out


def _to_field_unit(field_name: str, value: float, unit: str) -> float:
    """Convert a value with a label unit into the field's MFP unit."""
    wants_mg = field_name in _MG_FIELDS
    if unit == "mg":
        return value if wants_mg else value / 1000.0
    if unit in ("mcg", "µg"):
        return value / 1000.0 if wants_mg else value / 1_000_000.0
    # grams or no unit given: assume the label's natural unit for the row
    if unit == "g" and wants_mg:
        return value * 1000.0
    return value


def _column_order(text: str) -> tuple[int, int]:
    """Return (serving column index, per-100 g column index) from the header row."""
    serving = re.search(r"per\s+serv", text, re.I)
    hundred = re.search(r"per\s+100", text, re.I)
    if serving and hundred and hundred.start() < serving.start():
        return 1, 0
    return 0, 1


def parse_label(text: str) -> ParsedLabel:
    """Parse the text of a nutrition information panel.

    Handles the common Australian/UK layout::

        Avg Qty            Per Serving   Per 100g
        Energy (kJ)        2680kJ (641Cal)   620kJ (148Cal)
        Protein (g)        36.9g         8.5g
        Fat, total (g)     22.2g         5.1g
        - saturated (g)    9.4g          2.2g
        ...

    Only the first numeric column is required. Energy may be given in kJ,
    kcal/Cal, or both. Raises ``ValueError`` if no energy row is found.
    """
    serving_col, hundred_col = _column_order(text)
    serving: dict[str, float] = {}
    hundred: dict[str, float] = {}
    seen: set[str] = set()

    for raw_line in text.splitlines():
        label, values_text = _split_label_and_values(raw_line)
        if not label or not values_text:
            continue
        field_name = next((name for pat, name in _ROW_PATTERNS if pat.search(label)), None)
        if field_name is None or field_name in seen:
            continue
        numbers = _numbers(values_text)
        if not numbers:
            continue
        seen.add(field_name)

        if field_name == "energy":
            kj = [v for v, u in numbers if u == "kj"]
            kcal = [v for v, u in numbers if u in ("kcal", "cal", "calories")]
            unitless = [v for v, u in numbers if u == ""]
            if not kj and not kcal:
                # No units on the row: read the "(kJ)"/"(kcal)" hint from the label.
                if re.search(r"kcal|calories|\bcal\b", raw_line, re.I):
                    kcal = unitless
                else:
                    kj = unitless
            for col, store in ((serving_col, serving), (hundred_col, hundred)):
                if col < len(kj):
                    store["energy_kj"] = kj[col]
                if col < len(kcal):
                    store["calories"] = kcal[col]
            continue

        for col, store in ((serving_col, serving), (hundred_col, hundred)):
            if col < len(numbers):
                value, unit = numbers[col]
                store[field_name] = _to_field_unit(field_name, value, unit)

    if "calories" not in serving and "energy_kj" not in serving:
        raise ValueError("No energy row (kJ or kcal) found in label text")

    per_serving = _facts_from_columns(serving)
    per_100g = _facts_from_columns(hundred) if ("calories" in hundred or "energy_kj" in hundred) else None
    if per_100g is not None:
        per_serving.serving_weight_g = derive_serving_weight_g(per_serving, per_100g)
    return ParsedLabel(per_serving=per_serving, per_100g=per_100g)


def _facts_from_columns(values: dict[str, float]) -> NutritionFacts:
    values = dict(values)
    if "calories" not in values:
        values["calories"] = kj_to_kcal(values["energy_kj"])
    return NutritionFacts(**values)
