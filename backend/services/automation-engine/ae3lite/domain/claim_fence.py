"""Идентичность одного захвата AE3.

``process_run_id`` отличает запуск процесса. ``claim_generation`` отличает
повторный claim того же процесса. Право записи — пара
``(claimed_by, claim_generation)``. Совпадение этой пары перед HTTP не является
end-to-end fencing MQTT или прошивки.
"""

from __future__ import annotations

from typing import Any


def claim_owner(task: Any) -> str:
    return str(getattr(task, "claimed_by", None) or "").strip()


def claim_generation(task: Any) -> int:
    return int(getattr(task, "claim_generation", 0) or 0)


def same_claim_token(left: Any, right: Any) -> bool:
    owner = claim_owner(left)
    return bool(owner) and owner == claim_owner(right) and claim_generation(left) == claim_generation(right)
