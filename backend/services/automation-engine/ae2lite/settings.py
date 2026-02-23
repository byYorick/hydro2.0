"""AE2-Lite settings helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def _coerce_scalar(raw: str) -> Any:
    value = raw.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip("'\"")


def load_limits(path: Path | None = None) -> Dict[str, Any]:
    target = path or (Path(__file__).resolve().parent / "config" / "limits.yaml")
    if not target.exists():
        return {}

    parsed: Dict[str, Any] = {}
    current_section: Dict[str, Any] | None = None
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if raw_line.startswith("  ") and current_section is not None and ":" in line:
            key, value = line.split(":", 1)
            current_section[key.strip()] = _coerce_scalar(value)
            continue
        if line.endswith(":"):
            section = line[:-1].strip()
            parsed[section] = {}
            current_section = parsed[section]
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            parsed[key.strip()] = _coerce_scalar(value)
            current_section = None
    return parsed


__all__ = ["load_limits"]
