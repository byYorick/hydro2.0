"""Общая нормализация workflow-phase key для доменных сервисов AE3-Lite.

Канонические ключи: ``"solution_fill"``, ``"tank_recirc"``,
``"irrigation"``, ``"generic"``.
"""

from __future__ import annotations

from typing import Any


def normalize_phase_key(raw: Any) -> str:
    """Возвращает канонический phase key для сырой строки ``workflow_phase``.

    Преобразует имена workflow phase, включая legacy-алиасы, в один из четырёх
    канонических ключей, используемых в correction config и process calibration.
    """
    phase = str(raw or "").strip().lower()
    if phase in {"tank_filling", "solution_fill"}:
        return "solution_fill"
    if phase in {"tank_recirc", "prepare_recirculation"}:
        return "tank_recirc"
    if phase in {"irrigating", "irrigation", "irrig_recirc"}:
        return "irrigation"
    return phase or "generic"
