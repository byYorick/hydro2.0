"""E255: в живом индексе один канон автоматики — ae4.md."""

from __future__ import annotations

import re
from pathlib import Path


def _doc_ai_root() -> Path:
    candidates: list[Path] = [Path("/doc_ai")]
    here = Path(__file__).resolve()
    try:
        candidates.append(here.parents[6] / "doc_ai")
    except IndexError:
        pass
    candidates.append(Path("/home/georgiy/esp/hydro/hydro2.0/doc_ai"))
    for path in candidates:
        if (path / "INDEX.md").is_file():
            return path
    raise AssertionError(
        "doc_ai/INDEX.md не найден (ожидался mount /doc_ai или путь репозитория)"
    )


def test_e255_index_has_no_canonical_ae3lite_link() -> None:
    index = (_doc_ai_root() / "INDEX.md").read_text(encoding="utf-8")
    assert "ae3lite.md" not in index


def test_e255_no_second_canonical_automation_beside_ae4() -> None:
    """Поиск по doc_ai вне 00_ARCHIVE (эквивалент rg в отчёте)."""
    doc_ai = _doc_ai_root()
    pattern = re.compile(r"(?i)(статус|status).{0,40}canonical")
    hits: list[str] = []
    scanned = 0
    for path in sorted(doc_ai.rglob("*.md")):
        if "00_ARCHIVE" in path.parts:
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not pattern.search(line):
                continue
            loc = f"{path.relative_to(doc_ai)}:{lineno}:{line.strip()}"
            if "ae4.md" in loc:
                continue
            if re.search(r"ae3lite|AE3-Lite|машине стадий", loc, re.I):
                hits.append(loc)
            if "/AE3_" in loc or "ae3lite.md" in loc:
                hits.append(loc)
    print(f"E255 scanned={scanned} hits={len(hits)}")
    for item in hits:
        print(item)
    assert hits == [], f"unexpected canonical automation hits: {hits}"
