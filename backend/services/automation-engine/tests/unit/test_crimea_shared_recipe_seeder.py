"""Компромиссный рецепт салата и клубники сверяется с текстом сидера, без выдуманных коридоров."""

from pathlib import Path


def _recipe_block() -> str:
    source = (
        Path(__file__).resolve().parents[5]
        / "backend/laravel/database/seeders/ExtendedRecipesCyclesSeeder.php"
    ).read_text(encoding="utf-8")
    marker = "'name' => 'Салат и клубника, капля, Крым'"
    start = source.index(marker)
    end = source.index("'plant_slugs' => ['lettuce', 'strawberry']", start)
    # Блок рецепта до конца массива фаз: следующий элемент верхнего уровня уже закрывает recipeConfigs.
    tail = source.index("],\n        ];", start)
    return source[start:tail]


def test_shared_crimea_recipe_uses_compromise_chemistry_and_documented_bounds() -> None:
    block = _recipe_block()
    assert "'ph' => ['min' => 5.8, 'max' => 6.0, 'target' => 5.9]" in block
    assert "'ec' => ['min' => 1.4, 'max' => 1.6, 'target' => 1.5]" in block
    assert "'mode' => 'SUBSTRATE'" in block
    assert "'drain_to_waste' => true" in block
    assert "'drain_target_percent' => 20" in block
    assert "'interval_sec' => 3600" in block
    assert "'duration_sec' => 60" in block
    assert "'warn_c' => 26" in block
    assert "'stop_c' => 32" in block
    assert "'overheat_emergency_temp_c' => 32" in block
    assert "'heat_ceiling_day_c' => 25" in block
    assert "'temp_air' => ['min' => 18, 'max' => 22, 'target' => 20]" in block
    assert "'solution_temp' => ['min' => 18, 'max' => 22, 'target' => 20]" in block
    assert "консервативн" in block
    assert "AGRONOMY_CRIMEA" in block
    assert "RECIRC" not in block
    assert "осмос" in block
    assert "базовая EC около 0" in block
