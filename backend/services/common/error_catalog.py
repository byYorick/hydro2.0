"""Локализация error_code по backend/error_codes.json (контракт фазы 2)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

def _candidate_paths(filename: str) -> tuple[Path, ...]:
    """Build candidate paths without assuming a fixed monorepo depth."""
    here = Path(__file__).resolve()
    candidates: list[Path] = [Path("/app") / filename]
    for root in here.parents:
        candidates.append(root / filename)
    return tuple(candidates)


_CATALOG_PATHS = _candidate_paths("error_codes.json")
_RAW_TRANSLATION_PATHS = _candidate_paths("api_error_raw_translations.json")


@lru_cache(maxsize=1)
def _codes_by_code() -> dict[str, dict[str, str]]:
    path = next((candidate for candidate in _CATALOG_PATHS if candidate.is_file()), None)
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, str]] = {}
    for row in data.get("codes", []):
        if not isinstance(row, dict):
            continue
        code = _normalize_code(str(row.get("code") or ""))
        if code:
            result[code] = {
                "title": str(row.get("title") or "").strip(),
                "message": str(row.get("message") or "").strip(),
            }
    return result


@lru_cache(maxsize=1)
def _raw_translations() -> dict[str, Any]:
    path = next((candidate for candidate in _RAW_TRANSLATION_PATHS if candidate.is_file()), None)
    if path is None:
        return {"code_by_exact_message": {}, "exact": {}, "patterns": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "code_by_exact_message": data.get("code_by_exact_message") or {},
        "exact": data.get("exact") or {},
        "patterns": data.get("patterns") or [],
    }


def _normalize_code(code: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9_]", "_", str(code or "").strip().lower())
    return normalized.strip("_")


def _looks_localized(message: str) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", message))


def _infer_code_from_message(message: str) -> str | None:
    trimmed = message.strip()
    if not trimmed:
        return None
    by_message = _raw_translations().get("code_by_exact_message") or {}
    raw_code = by_message.get(trimmed)
    if isinstance(raw_code, str) and raw_code.strip():
        return _normalize_code(raw_code)
    return None


def _translate_raw_message(message: str) -> str | None:
    raw = _raw_translations()
    exact = raw.get("exact") or {}
    if message in exact:
        return str(exact[message])

    for pattern in raw.get("patterns") or []:
        if not isinstance(pattern, dict):
            continue
        regex = str(pattern.get("regex") or "")
        replacement = str(pattern.get("message") or "")
        if not regex or not replacement:
            continue
        # JSON-паттерны используют $1/$2 (PHP preg_replace); в Python re.sub нужны \1/\2.
        replacement = re.sub(r"\$(\d+)", r"\\\1", replacement)
        translated = re.sub(regex, replacement, message, count=1, flags=re.IGNORECASE)
        if translated != message:
            return translated

    return None


def present_error(code: str | None, raw_message: str | None = None) -> dict[str, Any]:
    """Возвращает code, title, message, human_error_message для API-ответа."""
    normalized = _normalize_code(code)
    if not normalized and raw_message:
        normalized = _infer_code_from_message(str(raw_message)) or ""

    entry = _codes_by_code().get(normalized) if normalized else None
    catalog_message = entry.get("message") if entry else ""
    title = entry.get("title") if entry and entry.get("title") else "Системная ошибка"

    raw = str(raw_message or "").strip()
    if raw and _looks_localized(raw):
        message = raw
    elif catalog_message:
        message = catalog_message
    elif raw:
        translated = _translate_raw_message(raw)
        message = translated if translated else raw
    elif normalized:
        message = f"Внутренняя ошибка системы (код: {normalized})."
    else:
        message = None

    return {
        "code": normalized or None,
        "title": title,
        "message": message,
        "human_error_message": message,
    }


def enrich_error_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Дополняет dict ответа полями message / human_error_message по каталогу."""
    if not isinstance(payload, dict):
        return payload

    code = payload.get("code") or payload.get("error_code") or payload.get("error")
    raw_message = payload.get("message") or payload.get("error_message")
    if not isinstance(code, str) or not str(code).strip():
        if isinstance(raw_message, str) and raw_message.strip():
            code = _infer_code_from_message(raw_message) or "api_error"
        else:
            return payload
    elif not str(code).strip():
        return payload

    presentation = present_error(str(code), str(raw_message) if isinstance(raw_message, str) else None)
    enriched = dict(payload)
    if presentation["code"]:
        enriched["code"] = presentation["code"]
        enriched["error"] = presentation["code"]
    if presentation["message"]:
        enriched["message"] = presentation["message"]
        enriched["human_error_message"] = presentation["message"]
    if presentation["title"]:
        enriched["title"] = presentation["title"]
    enriched.setdefault("status", "error")
    return enriched
