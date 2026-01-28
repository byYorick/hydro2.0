"""Tests for legacy SQL string bans."""
from pathlib import Path


def test_legacy_sql_strings_are_not_present() -> None:
    banned_tokens = [
        "zone_recipe_instances",
        "recipe_phases",
        "zone_channel_bindings",
        "zone_infrastructure",
        "recipe_stage_maps",
    ]

    root = Path(__file__).resolve().parents[1]
    hits: list[tuple[str, str]] = []

    for path in root.rglob("*.py"):
        if path.name.startswith("test_"):
            continue
        if "__pycache__" in path.parts:
            continue

        content = path.read_text(encoding="utf-8", errors="ignore")
        for token in banned_tokens:
            if token in content:
                hits.append((str(path), token))

    assert not hits, f"Legacy SQL references found: {hits}"
