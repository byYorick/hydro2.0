"""Existing correction defaults and component aliases; shared immutable values."""

import logging

_logger = logging.getLogger("ae3lite.domain.services.correction_planner")

# ── Значения по умолчанию для расчёта доз (5.1: именованные константы вместо magic numbers) ──

#: Жёсткий верхний предел для одной EC-дозы, если correction_config.max_ec_dose_ml отсутствует.
_DEFAULT_MAX_EC_DOSE_ML: float = 50.0

#: Жёсткий верхний предел для одной pH-дозы, если correction_config.max_ph_dose_ml отсутствует.
_DEFAULT_MAX_PH_DOSE_ML: float = 20.0

#: Дефолтный cap длительности одной дозы (мс). Совпадает с firmware
#: `CORRECTION_NODE_ACTUATOR_MAX_DURATION_MS` / NodeConfig `safe_limits.max_duration_ms`
#: для ph_node/ec_node (60 с). AE3 обязан планировать `params.ml` так, чтобы
#: `ml / ml_per_sec * 1000` не превышал согласованный cap до отправки команды.
_DEFAULT_MAX_DOSE_MS: int = 60_000

#: EMA-фильтр производной, когда ``derivative_filter_alpha`` отсутствует в конфиге.
#: Явные ``0.0`` / ``1.0`` из конфига уважаются; ``or 1.0`` нельзя — затирает ``0.0``.
_DEFAULT_DERIVATIVE_FILTER_ALPHA: float = 0.35

# ── Порядок fallback-выбора EC-компонентов (5.3) ──────────────────────────────

#: Предпочтительный порядок EC-компонентов, когда ec_component_policy не настроен.
#: Компоненты вне этого списка добавляются после перечисленных в алфавитном порядке.
_EC_COMPONENT_DEFAULT_ORDER: tuple[str, ...] = ("npk", "a", "b", "calcium", "magnesium", "micro", "trace")
_EC_COMPONENT_LEGACY_ALIAS_MAP: dict[str, str] = {
    "a": "npk",
    "b": "calcium",
    "c": "magnesium",
    "d": "micro",
}


_EC_GAIN_COMPONENT_SKIP = frozenset({"", "ph", "none", "single", "multi_sequential", "multi_parallel"})
