"""Contract test: validate AE3 read-model requirements against Laravel-owned schema snapshot.

Laravel дампит актуальную схему БД в ``schemas/automation_read_model_schema.json``
(через ``AutomationReadModelSchemaTest.php``). Этот тест валидирует: все таблицы / колонки /
типы / enum-значения, на которые опирается AE3, присутствуют в БД.

Если Laravel удалит/переименует колонку, от которой зависит AE3 — этот тест упадёт в CI
раньше, чем runtime-ошибка долетит до production.

Обновить snapshot:
    docker compose -f backend/docker-compose.dev.yml exec \\
      -e UPDATE_SCHEMA_SNAPSHOT=1 laravel \\
      php artisan test --filter=AutomationReadModelSchemaTest

После этого проверить, что ``laravel_schema_contract.py`` обновлён под новые колонки/enum.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from ae3lite.infrastructure.read_models.laravel_schema_contract import (
    ALL_TABLES,
    TYPE_FAMILIES,
    Table,
)


def _candidate_paths() -> tuple[Path, ...]:
    here = Path(__file__).resolve()
    candidates = [Path("/schemas/automation_read_model_schema.json")]  # docker-compose mount

    # CI / host: подняться до git root (backend/services/automation-engine → hydro2.0).
    for depth in (3, 4):
        try:
            candidates.append(here.parents[depth] / "schemas" / "automation_read_model_schema.json")
        except IndexError:
            continue
    return tuple(candidates)


SNAPSHOT_CANDIDATES: tuple[Path, ...] = _candidate_paths()


def _load_snapshot() -> dict[str, Any]:
    override = os.environ.get("AE_READ_MODEL_SNAPSHOT_PATH")
    if override:
        return json.loads(Path(override).read_text(encoding="utf-8"))

    for candidate in SNAPSHOT_CANDIDATES:
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))

    pytest.skip(
        "schemas/automation_read_model_schema.json отсутствует. "
        "Сгенерируй через AutomationReadModelSchemaTest.php c UPDATE_SCHEMA_SNAPSHOT=1."
    )
    raise AssertionError("unreachable")  # pragma: no cover


def _column_type_compatible(snapshot_column: dict[str, Any], expected_family: str) -> bool:
    allowed = TYPE_FAMILIES[expected_family]
    return (
        snapshot_column.get("data_type") in allowed
        or snapshot_column.get("udt_name") in allowed
    )


@pytest.fixture(scope="module")
def snapshot() -> dict[str, Any]:
    return _load_snapshot()


def test_snapshot_version_supported(snapshot: dict[str, Any]) -> None:
    assert snapshot.get("version") == 1, (
        f"Unsupported snapshot version={snapshot.get('version')!r}; "
        "regenerate snapshot after Laravel-side version bump."
    )


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda t: t.name)
def test_table_present_in_snapshot(snapshot: dict[str, Any], table: Table) -> None:
    tables = snapshot.get("tables", {})
    assert table.name in tables, (
        f"Таблица {table.name!r} не найдена в snapshot. "
        "Либо Laravel-миграция её не создала, либо удалена. "
        "Если это breaking change — AE3 ДОЛЖЕН тоже перестать её читать (обнови laravel_schema_contract.py)."
    )


_STRICT_NULLABILITY = os.environ.get("AE_READ_MODEL_CONTRACT_STRICT_NULLABILITY") == "1"


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda t: t.name)
def test_required_columns_present_and_typed(snapshot: dict[str, Any], table: Table) -> None:
    snap_table = snapshot.get("tables", {}).get(table.name)
    if snap_table is None:
        pytest.skip(f"table {table.name} missing (covered by test_table_present_in_snapshot)")
    snap_columns: dict[str, Any] = snap_table.get("columns", {})

    missing: list[str] = []
    wrong_type: list[str] = []
    wrong_nullability: list[str] = []

    for col in table.columns:
        snap_col = snap_columns.get(col.name)
        if snap_col is None:
            missing.append(col.name)
            continue
        if not _column_type_compatible(snap_col, col.type_family):
            wrong_type.append(
                f"{col.name}: expected family={col.type_family} "
                f"(allowed: {sorted(TYPE_FAMILIES[col.type_family])}), "
                f"got data_type={snap_col.get('data_type')!r} / udt_name={snap_col.get('udt_name')!r}"
            )
        if not col.nullable and snap_col.get("is_nullable", "YES") == "YES":
            wrong_nullability.append(
                f"{col.name}: AE3 ждёт NOT NULL, но в snapshot is_nullable=YES"
            )

    assert not missing, f"{table.name}: отсутствуют колонки {missing}"
    assert not wrong_type, f"{table.name}: несовместимые типы:\n  " + "\n  ".join(wrong_type)

    if _STRICT_NULLABILITY:
        assert not wrong_nullability, (
            f"{table.name}: рассогласование NOT NULL (STRICT):\n  "
            + "\n  ".join(wrong_nullability)
        )


@pytest.mark.parametrize(
    "table", [t for t in ALL_TABLES if t.enum_values], ids=lambda t: t.name
)
def test_enum_literal_columns_present(snapshot: dict[str, Any], table: Table) -> None:
    """Для таблиц с контрактными enum-колонками: сам столбец обязан существовать.

    Проверка конкретных литералов (CHECK-constraints / enum values) требует runtime-БД;
    это отдельный integration-тест. Здесь гарантируем хотя бы наличие колонки.
    """
    snap_columns = snapshot.get("tables", {}).get(table.name, {}).get("columns", {})
    for column_name in table.enum_values:
        assert column_name in snap_columns, (
            f"{table.name}.{column_name}: enum-колонка отсутствует, "
            f"но AE3 ждёт значения {sorted(table.enum_values[column_name])}."
        )
