import json
import math
import sys
from typing import Any, Dict


def canonical_json_payload(payload: Dict[str, Any]) -> str:
    data = dict(payload)
    data.pop("sig", None)
    return _encode_value(data)


def _encode_value(value: Any) -> str:
    if value is None:
        return "null"

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, int):
        return str(value)

    if isinstance(value, float):
        return _format_number(value)

    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    if isinstance(value, (list, tuple)):
        items = [_encode_value(item) for item in value]
        return "[" + ",".join(items) + "]"

    if isinstance(value, dict):
        keys = sorted(value.keys(), key=lambda k: str(k))
        items = []
        for key in keys:
            key_str = str(key)
            encoded_key = json.dumps(key_str, ensure_ascii=False, separators=(",", ":"))
            items.append(encoded_key + ":" + _encode_value(value[key]))
        return "{" + ",".join(items) + "}"

    raise ValueError(f"Unsupported type for canonical JSON: {type(value)}")


def _format_number(value: float) -> str:
    if math.isnan(value) or math.isinf(value):
        return "null"

    if float(int(value)) == value:
        return str(int(value))

    formatted = format(value, ".15g")
    try:
        parsed = float(formatted)
    except ValueError:
        parsed = value

    if not _compare_double(parsed, value):
        formatted = format(value, ".17g")

    return formatted.lower()


def _compare_double(a: float, b: float) -> bool:
    max_val = max(abs(a), abs(b))
    return abs(a - b) <= max_val * sys.float_info.epsilon
