"""Tests for nutrition panel parsing and unit handling."""

import pytest

from connectors.myfitnesspal.nutrition import (
    NutritionFacts,
    derive_serving_weight_g,
    kj_to_kcal,
    parse_label,
)

HELLOFRESH_LABEL = """
Nutrition
Avg Qty          Per Serving       Per 100g
Energy (kJ)      2680kJ (641Cal)   620kJ (148Cal)
Protein (g)      36.9g             8.5g
Fat, total (g)   22.2g             5.1g
- saturated (g)  9.4g              2.2g
Carbohydrate (g) 70.7g             16.4g
- sugars (g)     9g                2.1g
Sodium (mg)      1580mg            366mg
Dietary Fibre (g) 8.5g             2g
The quantities provided above are averages only.
"""


def test_parse_hellofresh_label_per_serving():
    facts = parse_label(HELLOFRESH_LABEL).per_serving
    assert facts.calories == 641
    assert facts.energy_kj == 2680
    assert facts.protein_g == 36.9
    assert facts.fat_g == 22.2
    assert facts.saturated_fat_g == 9.4
    assert facts.carbohydrates_g == 70.7
    assert facts.sugars_g == 9
    assert facts.sodium_mg == 1580
    assert facts.fibre_g == 8.5
    assert facts.trans_fat_g is None


def test_parse_hellofresh_label_per_100g_and_serving_weight():
    parsed = parse_label(HELLOFRESH_LABEL)
    assert parsed.per_100g is not None
    assert parsed.per_100g.calories == 148
    assert parsed.per_100g.sodium_mg == 366
    # 2680 kJ per serving / 620 kJ per 100 g -> 432 g serving
    assert parsed.per_serving.serving_weight_g == 432


def test_parse_kj_only_derives_kcal():
    facts = parse_label("Energy 1000kJ\nProtein 10g").per_serving
    assert facts.calories == kj_to_kcal(1000) == 239.0
    assert facts.energy_kj == 1000


def test_parse_unitless_values_use_label_unit_hint():
    facts = parse_label("Energy (kcal) 250\nSodium (mg) 400\nFat (g) 3.5").per_serving
    assert facts.calories == 250
    assert facts.energy_kj is None
    assert facts.sodium_mg == 400
    assert facts.fat_g == 3.5


def test_parse_converts_units_to_mfp_units():
    facts = parse_label("Energy 100kcal\nSodium 1.5g\nFibre 500mg").per_serving
    assert facts.sodium_mg == 1500
    assert facts.fibre_g == 0.5


def test_parse_per_100g_column_first():
    text = "Per 100g   Per Serving\nEnergy 100kcal 300kcal\nProtein 2g 6g"
    parsed = parse_label(text)
    assert parsed.per_serving.calories == 300
    assert parsed.per_serving.protein_g == 6
    assert parsed.per_100g.calories == 100
    assert parsed.per_serving.serving_weight_g == 300


def test_parse_requires_energy_row():
    with pytest.raises(ValueError):
        parse_label("Protein 10g\nFat 5g")


def test_derive_serving_weight_falls_back_to_nutrients():
    per_serving = NutritionFacts(calories=0, protein_g=20)
    per_100g = NutritionFacts(calories=0, protein_g=5)
    assert derive_serving_weight_g(per_serving, per_100g) == 400


def test_from_kilojoules():
    facts = NutritionFacts.from_kilojoules(2680, protein_g=36.9)
    assert facts.calories == 640.5
    assert facts.energy_kj == 2680
    assert facts.nutrient_items() == {"calories": 640.5, "protein_g": 36.9}
