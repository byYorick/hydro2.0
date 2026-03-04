# Задача: Переработка системы коррекции pH/EC — PID + Autotune + Надёжность

**Дата:** 2026-03-04
**Ветка:** `feature/correction-pid-rewrite`
**Статус:** ГОТОВ К РЕАЛИЗАЦИИ
**Обратная совместимость:** НЕ ТРЕБУЕТСЯ (проект в разработке)

---

## Контекст и мотивация

Текущая система pH/EC коррекции содержит критические дефекты, блокирующие нормальную работу:

1. **Ki=0 для всех зон** — P-контроллер без интегральной части. Гарантированная остаточная ошибка (steady-state offset). Система никогда не достигает точного target pH/EC.

2. **Один нулевой насос = весь EC batch не работает** — `correction_ec_batch.py:216` делает `return []` если ml_per_sec <= 0 для *любого* компонента. Если таблица `pump_calibrations` пуста (что есть сейчас в dev), вся EC-коррекция заблокирована.

3. **Autotune — мёртвый код с неверной логикой** — тройная блокировка (enable_autotune=False + mode="disabled" + env=0), алгоритм инвертирует логику Ki (уменьшает когда надо увеличивать), нижняя граница Ki=0.001 при init=0 внезапно включает интеграцию.

4. **Monotonic clock при восстановлении** — `pid_state` хранит `last_output_ms` как монотонное время. После перезапуска AE значение из БД больше текущего monotonic → elapsed_ms < 0 → дозирование заблокировано навсегда.

5. **dt_seconds без верхней границы** — если AE зависал, dt может быть 300-600 секунд, PID интегрирует огромный накопленный error.

---

## Архитектура решения

### Правильные PID-параметры

```
pH:  dead=0.05, close=0.30, far=1.0
     CLOSE: Kp=5.0, Ki=0.05, Kd=0.0
     FAR:   Kp=8.0, Ki=0.02, Kd=0.0
     max_output=20 ml, min_interval=90_000 ms, max_integral=20.0

EC:  dead=0.10, close=0.50, far=1.5
     CLOSE: Kp=30.0, Ki=0.30, Kd=0.0
     FAR:   Kp=50.0, Ki=0.10, Kd=0.0
     max_output=50 ml, min_interval=120_000 ms, max_integral=100.0
```

### Relay Autotune (Åström-Hägglund, 1984)

Вместо наивного ±5% — relay feedback метод:
1. Включить relay с амплитудой d (pH: 3 ml, EC: 10 ml) вместо PID
2. Дождаться 3 устойчивых полных колебания
3. Вычислить: `Ku = 4d / (π × Au)`, `Tu` = средний период
4. SIMC: `Kp = 0.45 × Ku`, `Ti = 0.83 × Tu`, `Ki = Kp / Ti`, `Kd = 0`
5. Сохранить в `zone_pid_configs`

### Исправление pid_state (wallclock)

Добавить столбец `last_dose_at TIMESTAMPTZ` в таблицу `pid_state`.
При сохранении: писать `NOW()` в `last_dose_at`.
При восстановлении: `seconds_since = (utcnow - last_dose_at).total_seconds()`, конвертировать в правильный monotonic offset.

### EC batch partial failure

Вместо `return []` при ml_per_sec <= 0 — пропустить компонент, продолжить с остальными.
Если все компоненты недоступны → тогда `return []`.

---

## Агент 1: PID Engine

### Цель
Переработать ядро PID-вычислений, добавить RelayAutotuner, исправить восстановление состояния после перезапуска.

### Документация для изучения
- `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` — контекст pH/EC целевых значений
- `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — архитектура AE

### Входные файлы (прочитать полностью)

| Файл | Строк | Что делает |
|------|-------|-----------|
| `backend/services/automation-engine/utils/adaptive_pid.py` | 358 | Основной PID класс |
| `backend/services/automation-engine/services/pid_state_manager.py` | 233 | Сохранение/восстановление состояния |
| `backend/services/automation-engine/services/pid_config_service.py` | ~328 | Загрузка конфига из БД с кешом |
| `backend/services/automation-engine/config/settings.py` | ~150 | Все константы |
| `backend/laravel/database/migrations/2026_01_23_000003_add_automation_engine_tables.php` | — | Схема pid_state |

---

### Задача 1.1: Переработать `utils/adaptive_pid.py`

**Что изменить:**

1. **Удалить `_apply_autotune()`** полностью — этот метод заменяется классом `RelayAutotuner`.

2. **Убрать поля autotune из `AdaptivePidConfig`**:
   - Удалить: `enable_autotune`, `autotune_mode`, `adaptation_rate`, `_init_zone_coeffs`
   - Убрать вызов `self._apply_autotune(...)` из `compute()`
   - Убрать `_autotune_guard_enabled` из `__init__`

3. **Исправить `derivative_filter_alpha`**: изменить дефолт в `AdaptivePidConfig` с `1.0` на `0.35` (0.35 = хороший баланс между шумоподавлением и откликом).

4. **Добавить `max_integral` в `AdaptivePidConfig`** со значением по умолчанию `100.0` — уже есть, но задокументировать связь с Ki.

5. **Добавить класс `RelayAutotuner`** в конец файла:

```python
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

@dataclass
class RelayAutotuneConfig:
    relay_amplitude_ml: float          # амплитуда relay в мл (pH: 3.0, EC: 10.0)
    min_cycles: int = 3                # минимум полных колебаний перед расчётом
    max_duration_sec: float = 7200.0   # таймаут 2 часа
    min_oscillation_amplitude: float = 0.02  # минимальная амплитуда для pH; для EC: 0.1
    # SIMC tuning factors:
    simc_kp_factor: float = 0.45       # Kp = simc_kp_factor * Ku
    simc_ti_factor: float = 0.83       # Ti = simc_ti_factor * Tu → Ki = Kp / Ti

@dataclass
class RelayAutotuneResult:
    kp: float
    ki: float
    kd: float = 0.0
    ku: float = 0.0           # ultimate gain
    tu_sec: float = 0.0       # ultimate period
    oscillation_amplitude: float = 0.0
    cycles_detected: int = 0
    duration_sec: float = 0.0

class RelayAutotuner:
    """
    Relay feedback autotune (Åström-Hägglund, 1984).
    Применяется ВМЕСТО PID во время процедуры автотюнинга.

    Алгоритм:
      1. Подаём relay output: +d если error > 0, -d если error < 0
      2. Фиксируем extrema (пики и впадины) по сменам знака производной
      3. После min_cycles полных колебаний вычисляем Ku и Tu
      4. Применяем SIMC правила: Kp = 0.45*Ku, Ti = 0.83*Tu, Ki = Kp/Ti
    """

    def __init__(self, config: RelayAutotuneConfig, setpoint: float, start_time_sec: float):
        self.config = config
        self.setpoint = setpoint
        self.start_time_sec = start_time_sec
        self._complete = False
        self._timed_out = False
        self._result: Optional[RelayAutotuneResult] = None

        # Для фиксации экстремумов:
        self._relay_state: int = 1            # +1 или -1
        self._extrema: List[float] = []       # значения extrema (в единицах setpoint)
        self._extrema_times: List[float] = [] # времена extrema
        self._last_error: Optional[float] = None
        self._zero_crossings: int = 0         # количество пересечений нуля

    def update(self, current_value: float, now_sec: float) -> Optional[float]:
        """
        Обновить автотюнер, вернуть relay output (в мл) или None если завершён.

        Returns:
            float: relay output (±relay_amplitude_ml)
            None: автотюнинг завершён (complete или timeout)
        """
        if self._complete or self._timed_out:
            return None

        elapsed = now_sec - self.start_time_sec
        if elapsed > self.config.max_duration_sec:
            self._timed_out = True
            logger.warning(
                "RelayAutotuner timed out after %.1f sec, %d extrema collected",
                elapsed, len(self._extrema)
            )
            return None

        error = self.setpoint - current_value

        # Смена знака ошибки (нулевое пересечение) → смена relay state
        if self._last_error is not None:
            if (error > 0 and self._last_error <= 0) or (error < 0 and self._last_error >= 0):
                self._relay_state *= -1
                self._zero_crossings += 1
                # Фиксируем последнее значение как extremum
                self._extrema.append(current_value)
                self._extrema_times.append(now_sec)

                # Проверяем достаточность данных
                if self._zero_crossings >= self.config.min_cycles * 2:
                    result = self._compute_params(elapsed)
                    if result is not None:
                        self._result = result
                        self._complete = True
                        return None

        self._last_error = error
        return float(self.config.relay_amplitude_ml * self._relay_state)

    def _compute_params(self, elapsed_sec: float) -> Optional[RelayAutotuneResult]:
        """Вычислить Kp, Ki по SIMC из собранных данных."""
        if len(self._extrema) < 4 or len(self._extrema_times) < 4:
            return None

        # Разделить на peaks и valleys
        peaks = self._extrema[0::2]    # чётные — пики
        valleys = self._extrema[1::2]  # нечётные — впадины

        if not peaks or not valleys:
            return None

        # Амплитуда колебаний Au
        Au = (max(peaks) - min(valleys)) / 2.0
        if Au < self.config.min_oscillation_amplitude:
            logger.warning(
                "RelayAutotuner: oscillation amplitude %.4f < min %.4f, insufficient response",
                Au, self.config.min_oscillation_amplitude
            )
            return None

        # Период Tu — среднее время между соседними extrema × 2
        periods = []
        for i in range(1, len(self._extrema_times)):
            periods.append((self._extrema_times[i] - self._extrema_times[i-1]) * 2.0)
        Tu = sum(periods) / len(periods) if periods else 0.0

        if Tu < 10.0:  # минимум 10 секунд
            logger.warning("RelayAutotuner: Tu=%.1f sec too small, ignoring", Tu)
            return None

        # SIMC формулы
        d = self.config.relay_amplitude_ml
        Ku = (4.0 * d) / (math.pi * Au)
        Kp = self.config.simc_kp_factor * Ku
        Ti = self.config.simc_ti_factor * Tu
        Ki = Kp / Ti if Ti > 0 else 0.0

        logger.info(
            "RelayAutotuner complete: Ku=%.3f Tu=%.1fs → Kp=%.3f Ki=%.4f Au=%.4f cycles=%d",
            Ku, Tu, Kp, Ki, Au, self._zero_crossings // 2
        )

        return RelayAutotuneResult(
            kp=round(Kp, 4),
            ki=round(Ki, 5),
            kd=0.0,
            ku=round(Ku, 4),
            tu_sec=round(Tu, 2),
            oscillation_amplitude=round(Au, 4),
            cycles_detected=self._zero_crossings // 2,
            duration_sec=round(elapsed_sec, 1),
        )

    @property
    def is_complete(self) -> bool:
        return self._complete

    @property
    def is_timed_out(self) -> bool:
        return self._timed_out

    @property
    def result(self) -> Optional[RelayAutotuneResult]:
        return self._result
```

---

### Задача 1.2: Обновить `config/settings.py`

**Изменить следующие значения** (все остальные поля не трогать):

```python
# pH PID — добавить Ki, исправить параметры
PH_PID_DEAD_ZONE: float = 0.05         # было 0.2 → теперь 0.05
PH_PID_CLOSE_ZONE: float = 0.30        # было 0.5 → теперь 0.30
PH_PID_KP_CLOSE: float = 5.0           # было 10.0
PH_PID_KI_CLOSE: float = 0.05          # было 0.0 → КРИТИЧНО: включить интегральное действие
PH_PID_KD_CLOSE: float = 0.0
PH_PID_KP_FAR: float = 8.0             # было 12.0
PH_PID_KI_FAR: float = 0.02            # было 0.0 → меньший Ki для FAR (избежать overshooting)
PH_PID_KD_FAR: float = 0.0
PH_PID_MAX_OUTPUT: float = 20.0        # было 50.0 → уменьшить: 20 ml за раз достаточно
PH_PID_MIN_INTERVAL_MS: int = 90_000   # было 60_000 → 90 сек: дать раствору перемешаться
PH_PID_MAX_INTEGRAL: float = 20.0      # новый параметр: ограничить windup
PH_PID_DERIVATIVE_FILTER_ALPHA: float = 0.35  # новый параметр: фильтр производной
# Удалить PH_PID_ENABLE_AUTOTUNE и PH_PID_ADAPTATION_RATE

# EC PID — добавить Ki, исправить параметры
EC_PID_DEAD_ZONE: float = float(os.getenv("EC_PID_DEAD_ZONE", "0.10"))  # было 0.05 → 0.10 (EC шумный)
EC_PID_CLOSE_ZONE: float = 0.50        # оставить
EC_PID_KP_CLOSE: float = 30.0          # было 100.0 → уменьшить
EC_PID_KI_CLOSE: float = 0.30          # было 0.0 → КРИТИЧНО: включить
EC_PID_KD_CLOSE: float = 0.0
EC_PID_KP_FAR: float = 50.0            # было 120.0
EC_PID_KI_FAR: float = 0.10            # было 0.0
EC_PID_KD_FAR: float = 0.0
EC_PID_MAX_OUTPUT: float = 50.0        # было 200.0 → консервативнее
EC_PID_MIN_INTERVAL_MS: int = 120_000  # было 60_000 → 2 мин: EC медленнее стабилизируется
EC_PID_MAX_INTEGRAL: float = 100.0     # новый параметр
EC_PID_DERIVATIVE_FILTER_ALPHA: float = 0.35  # новый параметр
# Удалить EC_PID_ENABLE_AUTOTUNE и EC_PID_ADAPTATION_RATE

# Общие PID параметры (заменить старые)
PID_ANTI_WINDUP_MODE: str = os.getenv("PID_ANTI_WINDUP_MODE", "conditional")
PID_BACK_CALCULATION_GAIN: float = 0.2
# Удалить PID_AUTOTUNE_MODE, PID_DERIVATIVE_FILTER_ALPHA (перенесены в per-type)

# Relay autotune параметры (новые)
PH_RELAY_AUTOTUNE_AMPLITUDE_ML: float = 3.0
PH_RELAY_AUTOTUNE_MIN_CYCLES: int = 3
PH_RELAY_AUTOTUNE_MAX_DURATION_SEC: float = 7200.0
PH_RELAY_AUTOTUNE_MIN_OSCILLATION: float = 0.02

EC_RELAY_AUTOTUNE_AMPLITUDE_ML: float = 10.0
EC_RELAY_AUTOTUNE_MIN_CYCLES: int = 3
EC_RELAY_AUTOTUNE_MAX_DURATION_SEC: float = 7200.0
EC_RELAY_AUTOTUNE_MIN_OSCILLATION: float = 0.10
```

Также обновить `build_pid_config_for_controller()` в `correction_controller_helpers.py`:
- Передавать `max_integral=settings.PH_PID_MAX_INTEGRAL`
- Убрать `enable_autotune`, `autotune_mode`, `adaptation_rate` из `AdaptivePidConfig(...)`
- Добавить `derivative_filter_alpha=settings.PH_PID_DERIVATIVE_FILTER_ALPHA`

---

### Задача 1.3: Исправить `services/pid_state_manager.py`

**Проблема:** `last_output_ms` хранится как монотонное время. После перезапуска AE `time.monotonic()` начинается с нуля, а значение из БД — большое → elapsed_ms < 0 → дозирование заблокировано.

**Решение:** Хранить `last_dose_at TIMESTAMPTZ` (wallclock) вместо `last_output_ms`.

**Изменения в `save_pid_state()`:**

Заменить сохранение `last_output_ms` → вместо этого вычислять wallclock и сохранять:

```python
# Если pid.last_output_ms > 0: вычислить wallclock момент последней дозы
# last_output_ms — monotonic ms прошлой дозы
# now_mono_ms — monotonic ms сейчас
# now_utc — текущий UTC timestamp
# last_dose_ago_sec = (now_mono_ms - pid.last_output_ms) / 1000.0
# last_dose_at = now_utc - timedelta(seconds=last_dose_ago_sec)

now_utc = datetime.utcnow()
now_mono_ms = int(time.monotonic() * 1000)
last_dose_at = None
if pid.last_output_ms > 0:
    last_dose_ago_sec = max(0.0, (now_mono_ms - pid.last_output_ms) / 1000.0)
    last_dose_at = now_utc - __import__('datetime').timedelta(seconds=last_dose_ago_sec)
```

SQL INSERT добавить столбец `last_dose_at`:
```sql
INSERT INTO pid_state (zone_id, pid_type, integral, prev_error, last_output_ms, last_dose_at, prev_derivative, stats, current_zone, updated_at)
VALUES ($1, $2, $3, $4, 0, $5, $6, $7, $8, NOW())
ON CONFLICT (zone_id, pid_type) DO UPDATE
SET integral = EXCLUDED.integral,
    prev_error = EXCLUDED.prev_error,
    last_dose_at = EXCLUDED.last_dose_at,
    prev_derivative = EXCLUDED.prev_derivative,
    stats = EXCLUDED.stats,
    current_zone = EXCLUDED.current_zone,
    updated_at = NOW()
```

**Изменения в `restore_pid_state()`:**

```python
# Загрузить last_dose_at из БД
last_dose_at = row.get('last_dose_at')
now_utc = datetime.utcnow()
now_mono_ms = int(time.monotonic() * 1000)

if last_dose_at is not None:
    seconds_since_last_dose = (now_utc - last_dose_at).total_seconds()
    min_interval_sec = pid.config.min_interval_ms / 1000.0
    remaining_interval_sec = min_interval_sec - seconds_since_last_dose
    if remaining_interval_sec > 0:
        # Нужно подождать ещё remaining_interval_sec → смоделировать last_output_ms
        pid.last_output_ms = now_mono_ms - int(seconds_since_last_dose * 1000)
        logger.info("Zone %s: PID %s restored, next dose in %.0f sec",
                    zone_id, pid_type, remaining_interval_sec)
    else:
        # Прошло больше чем min_interval → разрешаем сразу
        pid.last_output_ms = 0
else:
    pid.last_output_ms = 0

# Также восстановить prev_derivative (добавить в SELECT и восстановление)
pid.prev_derivative = float(state.get('prev_derivative') or 0.0)
```

**Удалить** весь блок с `_MONO_TS_FUTURE_TOLERANCE_MS` (больше не нужен).

**Обновить `load_pid_state()`:** добавить `last_dose_at, prev_derivative` в SELECT.

---

### Задача 1.4: Laravel-миграция для `pid_state`

Создать новую миграцию `2026_03_05_000001_update_pid_state_add_wallclock.php`:

```php
public function up(): void
{
    Schema::table('pid_state', function (Blueprint $table) {
        $table->timestampTz('last_dose_at')->nullable()->after('last_output_ms');
        $table->float('prev_derivative')->default(0.0)->after('prev_error');
    });
}

public function down(): void
{
    Schema::table('pid_state', function (Blueprint $table) {
        $table->dropColumn(['last_dose_at', 'prev_derivative']);
    });
}
```

---

### Критерии приёмки Агента 1

- [ ] `utils/adaptive_pid.py`: нет методов `_apply_autotune`, `_autotune_guard_enabled`. Есть класс `RelayAutotuner` с методом `update(current_value, now_sec) -> Optional[float]` и свойством `result: Optional[RelayAutotuneResult]`
- [ ] `utils/adaptive_pid.py`: `AdaptivePidConfig` не имеет полей `enable_autotune`, `autotune_mode`, `adaptation_rate`
- [ ] `config/settings.py`: `PH_PID_KI_CLOSE = 0.05`, `EC_PID_KI_CLOSE = 0.30`
- [ ] `services/pid_state_manager.py`: `save_pid_state()` записывает `last_dose_at` как UTC datetime, `restore_pid_state()` использует wallclock для корректного восстановления `last_output_ms`
- [ ] Миграция создана и применяется через `make migrate`

---

## Агент 2: Correction Flow & Reliability

### Цель
Исправить поток коррекции: частичный fallback для EC batch, dt-clamping, сброс интеграла при перерегулировании, сталость калибровок.

### Входные файлы (прочитать полностью)

| Файл | Строк | Что делает |
|------|-------|-----------|
| `backend/services/automation-engine/correction_ec_batch.py` | 439 | EC batch dosing (4 компонента) |
| `backend/services/automation-engine/correction_controller_helpers.py` | 245 | dt_seconds, command building |
| `backend/services/automation-engine/correction_controller_check_core.py` | 431 | Основная логика plan/gate |
| `backend/services/automation-engine/repositories/infrastructure_repository.py` | ~400 | Загрузка actuators из БД |
| `backend/services/automation-engine/config/settings.py` | ~150 | Константы |

---

### Задача 2.1: Исправить `correction_ec_batch.py` — partial failure

**Текущая проблема** (строки 187-216):
```python
for component in required_components:
    ...
    if ml_per_sec <= 0:
        return []   # ← блокирует ВСЕ компоненты
```

**Исправление:** Собирать `skipped_components` и продолжать. Только если все компоненты скипнуты — вернуть `[]`.

**Точные изменения:**

1. Заменить цикл сбора `ml_per_sec_by_component` (строки 187-217) на следующую логику:

```python
ml_per_sec_by_component: Dict[str, float] = {}
calibration_snapshot: Dict[str, Dict[str, Any]] = {}
skipped_components: List[str] = []

for component in required_components:
    actuator = component_actuators[component]
    ml_per_sec_raw = actuator.get("ml_per_sec")
    calibration_snapshot[component] = {
        "role": actuator.get("role"),
        "node_uid": actuator.get("node_uid"),
        "channel": actuator.get("channel"),
        "ml_per_sec_raw": ml_per_sec_raw,
        "k_ms_per_ml_l": actuator.get("k_ms_per_ml_l"),
    }
    try:
        ml_per_sec = float(ml_per_sec_raw)
    except (TypeError, ValueError):
        ml_per_sec = 0.0
    if ml_per_sec <= 0:
        logger.warning(
            "EC component skipped due to invalid pump calibration (ml_per_sec=%s), continuing with others",
            extra={"component": component, "ml_per_sec": ml_per_sec_raw, ...},
        )
        skipped_components.append(component)
        continue
    ml_per_sec_by_component[component] = ml_per_sec

if skipped_components:
    # Обновить required_components — исключить скипнутые
    remaining = [c for c in required_components if c not in skipped_components]
    if not remaining:
        logger.warning(
            "EC component batch skipped: all components have invalid calibration",
            extra={"skipped": skipped_components, "calibration_snapshot": calibration_snapshot},
        )
        return []
    # Попытаться продолжить с оставшимися, включая fallback к npk
    if "npk" in remaining:
        required_components = remaining
        logger.warning(
            "EC component batch: proceeding with partial components %s (skipped: %s)",
            remaining, skipped_components,
        )
    else:
        # Нет NPK и нет других доступных — нельзя дозировать
        logger.warning(
            "EC component batch skipped: npk not available after skipping invalid calibrations",
            extra={"remaining": remaining, "skipped": skipped_components},
        )
        return []
    # Пересчитать component_actuators
    component_actuators = {
        component: actuators[role_map[component]]
        for component in required_components
    }
```

2. После этого исправления `components_order = required_components` (уже обновлённый список) используется во всех дальнейших вычислениях без изменений.

---

### Задача 2.2: Исправить `correction_controller_helpers.py` — dt clamping

**Текущая проблема** (строка 65):
```python
return max(1.0, now - last_tick)  # нет верхней границы
```

**Исправление:**

```python
def get_dt_seconds_for_zone(controller: Any, zone_id: int) -> float:
    """Рассчитать dt между вызовами PID. Зажать в [5.0, 300.0] секунд."""
    now = time.monotonic()
    last_tick = controller._last_pid_tick.get(zone_id)
    controller._last_pid_tick[zone_id] = now

    if last_tick is None:
        return float(get_settings().MAIN_LOOP_SLEEP_SECONDS)

    raw_dt = now - last_tick
    # Нижняя граница: минимум 5 секунд (частота опроса сенсоров)
    # Верхняя граница: максимум 300 секунд (5 минут) — защита от зависаний AE
    clamped_dt = max(5.0, min(raw_dt, 300.0))

    if raw_dt > 300.0:
        logger.warning(
            "PID dt clamped: raw_dt=%.1f sec > 300s (AE may have been paused), using 300s",
            raw_dt,
            extra={"zone_id": zone_id, "raw_dt_sec": round(raw_dt, 1)},
        )

    return clamped_dt
```

Добавить константу в `settings.py`:
```python
PID_DT_MAX_SECONDS: float = 300.0  # верхняя граница dt между вызовами PID
PID_DT_MIN_SECONDS: float = 5.0    # нижняя граница
```

---

### Задача 2.3: Сброс интеграла при смене знака ошибки в `correction_controller_check_core.py`

**Проблема:** Если pH был ниже target (добавляли щёлочь), интеграл накопился положительный. Раствор перемешался — pH прыгнул выше target. Интеграл теперь неверный → замедляет коррекцию кислотой.

**Место:** В `check_and_correct_core()`, перед вычислением `pid.compute()`, добавить:

```python
# Если знак ошибки сменился относительно предыдущего compute — сбросить интеграл
# Это предотвращает накопленный windup после перерегулирования
prev_error = pid.prev_error
current_error = target - current_value
if (
    prev_error is not None
    and prev_error != 0.0
    and current_error != 0.0
    and (prev_error > 0) != (current_error > 0)  # смена знака
):
    logger.info(
        "PID integral reset: error sign changed (%.3f → %.3f), zone_id=%s, pid_type=%s",
        prev_error, current_error, zone_id, correction_type,
        extra={"zone_id": zone_id, "prev_error": prev_error, "current_error": current_error},
    )
    pid.integral = 0.0
```

Вставить ЭТО до строки вычисления `output = pid.compute(current_value, dt_seconds)`.

---

### Задача 2.4: Staleness warning в `repositories/infrastructure_repository.py`

Найти место где загружается `pump_calibration` из LATERAL JOIN. После получения результата добавить:

```python
# Проверить давность калибровки
valid_from = actuator.get("valid_from")
if valid_from:
    import datetime as dt
    age_days = (dt.datetime.utcnow() - valid_from).days if hasattr(valid_from, 'day') else 0
    if age_days > 30:
        logger.warning(
            "Pump calibration is stale: zone_id=%s, role=%s, age_days=%d",
            zone_id, actuator.get("role"), age_days,
            extra={
                "zone_id": zone_id,
                "role": actuator.get("role"),
                "calibration_age_days": age_days,
                "valid_from": str(valid_from),
            },
        )
```

---

### Задача 2.5: Добавить API endpoint для запуска relay autotune

Добавить endpoint в AE FastAPI (искать `api_runtime.py` или `api_manual_actions.py`):

```
POST /zones/{zone_id}/start-relay-autotune
Body: { "pid_type": "ph" | "ec" }
```

Логика:
1. Проверить что зона активна (цикл запущен)
2. Создать `RelayAutotuner` с параметрами из settings
3. Сохранить в `runtime_state` зоны: `_autotune_by_zone[zone_id] = autotuner`
4. Вернуть `{"status": "started", "zone_id": zone_id, "pid_type": pid_type}`

В `check_and_correct_core()` перед PID compute добавить:
```python
# Если идёт autotune — использовать relay output вместо PID
autotuner = controller._autotune_by_zone.get(zone_id)
if autotuner and not autotuner.is_complete and not autotuner.is_timed_out:
    relay_output = autotuner.update(current_value, time.monotonic())
    if relay_output is not None:
        # Использовать relay output как команду дозирования
        output = abs(relay_output)
        # ...формировать команду и отправлять
        return command_with_relay_output
    else:
        # Autotune завершён — сохранить результат
        if autotuner.is_complete and autotuner.result:
            await _save_autotune_result(zone_id, pid_type, autotuner.result, config_service)
        del controller._autotune_by_zone[zone_id]
```

Функция `_save_autotune_result()`:
```python
async def _save_autotune_result(zone_id, pid_type, result, config_service):
    """Сохранить результат autotune в zone_pid_configs."""
    await config_service.save_autotune_result(zone_id, pid_type, {
        "kp": result.kp,
        "ki": result.ki,
        "kd": result.kd,
        "source": "relay_autotune",
        "ku": result.ku,
        "tu_sec": result.tu_sec,
        "oscillation_amplitude": result.oscillation_amplitude,
        "cycles_detected": result.cycles_detected,
        "tuned_at": datetime.utcnow().isoformat(),
    })
```

Добавить `save_autotune_result()` в `pid_config_service.py`:
- UPDATE `zone_pid_configs SET config = config || jsonb_build_object('close', ...) WHERE zone_id = $1 AND type = $2`
- Обновить только `zone_coeffs.close.kp`, `zone_coeffs.close.ki`, `zone_coeffs.far.kp`, `zone_coeffs.far.ki`
- Инвалидировать кеш после сохранения

---

### Критерии приёмки Агента 2

- [ ] `correction_ec_batch.py`: при ml_per_sec <= 0 для одного компонента — продолжает с остальными, `return []` только если все компоненты недоступны
- [ ] `correction_controller_helpers.py`: `get_dt_seconds_for_zone()` возвращает значение из `[5.0, 300.0]` — тест с raw_dt=600 должен вернуть 300
- [ ] `correction_controller_check_core.py`: при смене знака ошибки `pid.integral` сбрасывается в 0
- [ ] Endpoint `POST /zones/{zone_id}/start-relay-autotune` существует и принимает `pid_type`
- [ ] `pid_config_service.py` содержит метод `save_autotune_result()`

---

## Агент 3: Тесты

### Цель
Написать полный набор unit-тестов и E2E-тестов, покрывающих исправленную систему. Все тесты должны быть зелёными.

### Входные файлы (прочитать для понимания паттернов)

| Файл | Зачем читать |
|------|-------------|
| `backend/services/automation-engine/test_adaptive_pid.py` | Паттерны существующих PID тестов |
| `backend/services/automation-engine/test_correction_ec_batch.py` | Паттерны EC batch тестов (если существует) |
| `tests/e2e/scenarios/automation_engine/E68_full_prod_path_strict_ec_ph_corrections.yaml` | Паттерн E2E сценария |
| `tests/e2e/scenarios/automation_engine/E61_fail_closed_corrections.yaml` | Паттерн fail-closed E2E |

Также прочитать:
- `backend/services/automation-engine/utils/adaptive_pid.py` (после изменений Агента 1)
- `backend/services/automation-engine/correction_ec_batch.py` (после изменений Агента 2)

---

### Задача 3.1: Переписать `test_adaptive_pid.py`

**Требования:** Покрыть все критические случаи нового PID с Ki > 0.

**Структура тестов:**

```python
# Хелпер для создания конфига
def _ph_pid_config(setpoint=6.0, **overrides) -> AdaptivePidConfig:
    zone_coeffs = {
        PidZone.DEAD: PidZoneCoeffs(kp=0, ki=0, kd=0),
        PidZone.CLOSE: PidZoneCoeffs(kp=5.0, ki=0.05, kd=0.0),
        PidZone.FAR: PidZoneCoeffs(kp=8.0, ki=0.02, kd=0.0),
    }
    return AdaptivePidConfig(
        setpoint=setpoint,
        dead_zone=0.05,
        close_zone=0.30,
        far_zone=1.0,
        zone_coeffs=overrides.get("zone_coeffs", zone_coeffs),
        max_output=overrides.get("max_output", 20.0),
        min_output=0.0,
        max_integral=overrides.get("max_integral", 20.0),
        anti_windup_mode=overrides.get("anti_windup_mode", "conditional"),
        min_interval_ms=0,  # без ограничения для тестов
        derivative_filter_alpha=0.35,
    )
```

**Обязательные тест-кейсы:**

```python
class TestAdaptivePidDeadZone:
    def test_dead_zone_no_output(self):
        """Если error < dead_zone → output = 0"""
        pid = AdaptivePid(_ph_pid_config())
        output = pid.compute(6.03, dt_seconds=60.0)  # error = -0.03 < 0.05
        assert output == 0.0

    def test_just_outside_dead_zone(self):
        """Если error чуть выше dead_zone → output > 0"""
        pid = AdaptivePid(_ph_pid_config())
        output = pid.compute(5.94, dt_seconds=60.0)  # error = 0.06 > 0.05
        assert output > 0.0

class TestAdaptivePidProportional:
    def test_p_term_scales_with_error(self):
        """P-term линейно зависит от ошибки при dt → 0 (integral ≈ 0)"""
        pid1 = AdaptivePid(_ph_pid_config())
        pid2 = AdaptivePid(_ph_pid_config())
        out1 = pid1.compute(5.5, dt_seconds=0.001)  # error=0.5, Kp=5 → ≈2.5 ml
        out2 = pid2.compute(5.7, dt_seconds=0.001)  # error=0.3, Kp=5 → ≈1.5 ml
        assert out1 > out2
        assert abs(out1 / out2 - (0.5 / 0.3)) < 0.1  # пропорциональность

class TestAdaptivePidIntegral:
    def test_integral_eliminates_steady_state_error(self):
        """
        P-only контроллер застрял бы на ошибке 0.05 (dead_zone).
        P+I должен интегрировать и превысить dead_zone.
        Симуляция: plant не реагирует на дозы (error = const = 0.07).
        При Ki=0.05 и dt=60s, после N шагов integral term заметно вырастет.
        """
        pid = AdaptivePid(_ph_pid_config(setpoint=6.0))
        # error = 0.07 (выше dead_zone=0.05, в CLOSE zone)
        # Симулируем что дозирование не меняет pH (worst case)
        outputs = []
        for _ in range(5):
            out = pid.compute(5.93, dt_seconds=60.0)  # error = 0.07
            outputs.append(out)

        # Integral должен нарастать → output увеличивается
        assert outputs[-1] > outputs[0], "output must grow over time due to integral accumulation"
        # P-term = 5.0 * 0.07 = 0.35, I-term after 5 steps = 0.05 * (0.07*300) = 1.05
        # Total after 5 steps should be significantly higher
        assert outputs[-1] > 0.35  # больше чем P-term alone

    def test_ki_zero_means_no_integral_growth(self):
        """С Ki=0 output одинаковый каждый шаг (P-only)"""
        coeffs = {
            PidZone.DEAD: PidZoneCoeffs(0, 0, 0),
            PidZone.CLOSE: PidZoneCoeffs(5.0, 0.0, 0.0),
            PidZone.FAR: PidZoneCoeffs(8.0, 0.0, 0.0),
        }
        pid = AdaptivePid(_ph_pid_config(zone_coeffs=coeffs))
        outputs = [pid.compute(5.93, dt_seconds=60.0) for _ in range(5)]
        # P-only: все outputs одинаковы
        assert all(abs(o - outputs[0]) < 1e-6 for o in outputs)

class TestAdaptivePidAntiWindup:
    def test_integral_clamped_by_max_integral(self):
        """integral не превышает max_integral"""
        pid = AdaptivePid(_ph_pid_config(max_integral=5.0))
        # Много итераций с большой ошибкой
        for _ in range(100):
            pid.compute(4.0, dt_seconds=60.0)  # error = 2.0 (FAR zone)
        assert abs(pid.integral) <= 5.0 + 1e-6

    def test_conditional_antiwindup_prevents_growth_at_saturation(self):
        """conditional anti-windup: при saturated output интеграл не растёт"""
        pid = AdaptivePid(_ph_pid_config(max_output=1.0, max_integral=100.0))
        integrals = []
        for _ in range(10):
            pid.compute(3.0, dt_seconds=60.0)  # очень большая ошибка → saturation
            integrals.append(pid.integral)
        # После saturation интеграл должен стабилизироваться
        last_5 = integrals[-5:]
        assert max(last_5) - min(last_5) < 1.0  # интеграл не растёт бесконтрольно

class TestAdaptivePidMinInterval:
    def test_min_interval_blocks_second_dose(self):
        """Второй compute() в пределах min_interval возвращает 0"""
        pid = AdaptivePid(_ph_pid_config())
        pid.config.min_interval_ms = 60_000
        out1 = pid.compute(5.5, dt_seconds=60.0)
        assert out1 > 0
        out2 = pid.compute(5.5, dt_seconds=1.0)  # через 1 сек
        assert out2 == 0.0

    def test_min_interval_allows_after_elapsed(self):
        """После min_interval дозирование разрешено"""
        import time
        pid = AdaptivePid(_ph_pid_config())
        pid.config.min_interval_ms = 100  # 100ms для теста
        out1 = pid.compute(5.5, dt_seconds=60.0)
        assert out1 > 0
        time.sleep(0.15)  # подождать 150ms
        out2 = pid.compute(5.5, dt_seconds=60.0)
        assert out2 > 0

class TestAdaptivePidEmergency:
    def test_emergency_stop_blocks_output(self):
        pid = AdaptivePid(_ph_pid_config())
        pid.emergency_stop()
        out = pid.compute(5.0, dt_seconds=60.0)
        assert out == 0.0

    def test_resume_after_emergency(self):
        pid = AdaptivePid(_ph_pid_config())
        pid.emergency_stop()
        pid.resume()
        out = pid.compute(5.0, dt_seconds=60.0)
        assert out > 0.0

class TestAdaptivePidSetpointChange:
    def test_integral_reset_on_large_setpoint_change(self):
        """Смена setpoint > 1e-3 → сброс интеграла"""
        pid = AdaptivePid(_ph_pid_config(setpoint=6.0))
        pid.integral = 10.0  # имитируем накопленный интеграл
        pid.update_setpoint(6.5)
        assert pid.integral == 0.0
        assert pid.prev_error is None

    def test_setpoint_no_reset_on_tiny_change(self):
        """Малое изменение setpoint не сбрасывает интеграл"""
        pid = AdaptivePid(_ph_pid_config(setpoint=6.0))
        pid.integral = 10.0
        pid.update_setpoint(6.0005)  # < 1e-3
        assert pid.integral == 10.0
```

---

### Задача 3.2: Создать `test_relay_autotune.py`

```python
import math
import pytest
from utils.adaptive_pid import RelayAutotuner, RelayAutotuneConfig

def _default_config(**overrides) -> RelayAutotuneConfig:
    return RelayAutotuneConfig(
        relay_amplitude_ml=overrides.get("relay_amplitude_ml", 3.0),
        min_cycles=overrides.get("min_cycles", 3),
        max_duration_sec=overrides.get("max_duration_sec", 7200.0),
        min_oscillation_amplitude=overrides.get("min_oscillation_amplitude", 0.02),
    )

class TestRelayAutotuner:
    def test_relay_output_matches_sign(self):
        """Relay output +d при error > 0, -d при error < 0"""
        at = RelayAutotuner(_default_config(), setpoint=6.0, start_time_sec=0.0)
        out = at.update(5.5, now_sec=0.0)  # error = 0.5 > 0 → relay_state=+1
        assert out == pytest.approx(3.0)

    def test_relay_flips_on_zero_crossing(self):
        """Relay state меняется при пересечении нуля"""
        at = RelayAutotuner(_default_config(), setpoint=6.0, start_time_sec=0.0)
        at.update(5.5, now_sec=0.0)   # error > 0
        at.update(6.1, now_sec=1.0)   # error < 0 → flip
        out = at.update(6.1, now_sec=2.0)
        assert out == pytest.approx(-3.0)

    def test_converges_after_min_cycles(self):
        """
        Симулируем простую first-order систему и проверяем что autotune завершается.
        Простая модель: pH меняется пропорционально relay output.
        """
        config = _default_config(min_cycles=3)
        at = RelayAutotuner(config, setpoint=6.0, start_time_sec=0.0)

        # Симуляция first-order системы: τ=120s, K=0.01 pH/ml
        value = 6.0
        tau = 120.0
        K_plant = 0.01
        dt = 10.0
        now = 0.0
        max_iter = 500

        for i in range(max_iter):
            relay_out = at.update(value, now_sec=now)
            if relay_out is None:
                break
            # Обновить plant: dy/dt = (K*u - y) / tau
            value += dt * (K_plant * relay_out - (value - 6.0)) / tau
            now += dt

        assert at.is_complete or at.is_timed_out, "autotune must finish"

        if at.is_complete:
            result = at.result
            assert result is not None
            assert result.kp > 0, "Kp must be positive"
            assert result.ki >= 0, "Ki must be non-negative"
            assert result.tu_sec > 0, "Tu must be positive"
            assert result.ku > 0, "Ku must be positive"

    def test_timeout_if_no_oscillations(self):
        """Если нет колебаний — timeout"""
        config = _default_config(max_duration_sec=10.0, min_cycles=3)
        at = RelayAutotuner(config, setpoint=6.0, start_time_sec=0.0)
        # Значение не меняется → нет нулевых пересечений
        for i in range(100):
            out = at.update(6.5, now_sec=float(i * 1.0))  # constant, no crossing
            if out is None:
                break
        assert at.is_timed_out
        assert not at.is_complete

    def test_result_none_if_not_complete(self):
        at = RelayAutotuner(_default_config(), setpoint=6.0, start_time_sec=0.0)
        assert at.result is None
        assert not at.is_complete

    def test_simc_formulas_correct(self):
        """Проверить SIMC формулы напрямую"""
        # Ku=20, Tu=100s → SIMC: Kp=9.0, Ti=83s, Ki=0.108
        config = RelayAutotuneConfig(
            relay_amplitude_ml=5.0,
            min_cycles=3,
            simc_kp_factor=0.45,
            simc_ti_factor=0.83,
        )
        at = RelayAutotuner(config, setpoint=6.0, start_time_sec=0.0)
        # Симулируем результат напрямую через _compute_params
        at._extrema = [6.5, 5.5, 6.5, 5.5, 6.5, 5.5, 6.5, 5.5]
        at._extrema_times = [50.0, 100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0]
        at._zero_crossings = 8
        result = at._compute_params(elapsed_sec=400.0)
        assert result is not None
        # Au = (6.5 - 5.5) / 2 = 0.5, Tu ≈ 100s
        # Ku = 4*5 / (π*0.5) ≈ 12.73, Kp = 0.45*12.73 ≈ 5.73
        assert result.kp == pytest.approx(5.73, abs=0.5)
        assert result.ki > 0
```

---

### Задача 3.3: Создать/обновить `test_correction_ec_batch_partial.py`

Проверить новое поведение partial failure:

```python
import pytest
from unittest.mock import MagicMock
from correction_ec_batch import build_ec_component_batch

def _mock_targets_with_all_components():
    """Targets с NPK, Ca, Mg, Micro компонентами (ratio 60/15/15/10)"""
    return {
        "nutrition": {
            "mode": "ratio_ec_pid",
            "components": {
                "npk":       {"ratio_pct": 60.0},
                "calcium":   {"ratio_pct": 15.0},
                "magnesium": {"ratio_pct": 15.0},
                "micro":     {"ratio_pct": 10.0},
            }
        }
    }

def _mock_actuators(missing_calibration_for: list = None):
    """Все 4 актуатора, с нулевой калибровкой для указанных"""
    missing_calibration_for = missing_calibration_for or []
    actuators = {}
    roles = {
        "npk": "ec_npk_pump",
        "calcium": "ec_calcium_pump",
        "magnesium": "ec_magnesium_pump",
        "micro": "ec_micro_pump",
    }
    for component, role in roles.items():
        ml_per_sec = 0.0 if component in missing_calibration_for else 1.0
        actuators[role] = {
            "role": role, "node_uid": f"node_{component}", "channel": f"ch_{component}",
            "node_channel_id": hash(component), "ml_per_sec": ml_per_sec,
        }
    return actuators

def _mock_build_cmd(actuator, correction_type, amount_ml):
    return {"cmd": "run_pump", "params": {"ml": amount_ml, "duration_ms": int(amount_ml * 1000)}}

class TestECBatchPartialCalibration:
    def test_all_calibrated_returns_4_commands(self):
        commands = build_ec_component_batch(
            targets=_mock_targets_with_all_components(),
            actuators=_mock_actuators(),
            total_ml=40.0,
            current_ec=1.0, target_ec=1.6,
            allowed_ec_components=None,
            build_correction_command=_mock_build_cmd,
        )
        assert len(commands) == 4

    def test_micro_missing_calibration_still_doses_others(self):
        """Если micro не откалиброван — NPK, Ca, Mg всё равно дозируются"""
        commands = build_ec_component_batch(
            targets=_mock_targets_with_all_components(),
            actuators=_mock_actuators(missing_calibration_for=["micro"]),
            total_ml=40.0,
            current_ec=1.0, target_ec=1.6,
            allowed_ec_components=None,
            build_correction_command=_mock_build_cmd,
        )
        components_dosed = {c["component"] for c in commands}
        assert "micro" not in components_dosed
        assert "npk" in components_dosed

    def test_all_missing_calibration_returns_empty(self):
        """Если ВСЕ насосы без калибровки — return []"""
        commands = build_ec_component_batch(
            targets=_mock_targets_with_all_components(),
            actuators=_mock_actuators(missing_calibration_for=["npk", "calcium", "magnesium", "micro"]),
            total_ml=40.0,
            current_ec=1.0, target_ec=1.6,
            allowed_ec_components=None,
            build_correction_command=_mock_build_cmd,
        )
        assert commands == []

    def test_npk_missing_calcium_available_falls_back_to_npk(self):
        """
        Если NPK недоступен, но Ca/Mg/Micro доступны — fallback к NPK-only не работает.
        Должен вернуть [] т.к. NPK — базовый компонент.

        (Это допустимое поведение: без NPK доза бессмысленна)
        """
        # NPK missing calibration, others fine
        actuators = _mock_actuators(missing_calibration_for=["npk"])
        commands = build_ec_component_batch(
            targets=_mock_targets_with_all_components(),
            actuators=actuators,
            total_ml=40.0,
            current_ec=1.0, target_ec=1.6,
            allowed_ec_components=None,
            build_correction_command=_mock_build_cmd,
        )
        assert commands == []
```

---

### Задача 3.4: E2E тест `E80_ph_pid_ki_convergence.yaml`

**Цель:** Подтвердить что pH PID с Ki > 0 устраняет steady-state error.

**Файл:** `tests/e2e/scenarios/automation_engine/E80_ph_pid_ki_convergence.yaml`

```yaml
name: E80_ph_pid_ki_convergence
description: |
  Проверяем что новый P+I PID для pH устраняет steady-state ошибку.
  1. Создаём зону с pH-насосами и настроенными калибровками
  2. Устанавливаем pH_target=5.80, инжектируем pH=5.50
  3. Ждём 2 коррекционных цикла
  4. Проверяем что zone_events типа PH_CORRECTED созданы
  5. Проверяем что dose > 0 (интегральное действие дало дозу)
  6. Проверяем что в логах нет "PID compute skipped: dead zone" для error=0.30

# DoD:
# - PH_CORRECTED события появились за время теста
# - В payload события integral_term > 0 (доказывает Ki работает)
# - Нет "blocked: integral=0" в логах

actions:
  - step: setup_vars
    type: set
    zone_id: ""
    gh_id: ""
    test_start: ""

  - step: get_greenhouse
    type: database_query
    query: "SELECT id FROM greenhouses LIMIT 1"
    save: gh_row
    expected_rows: 1

  - step: create_zone
    type: api_post
    endpoint: /api/zones
    payload:
      name: e2e-ph-pid-ki-${TIMESTAMP_S}
      greenhouse_id: ${gh_row.0.id}
    save: zone_resp

  - step: set_ctx
    type: set
    zone_id: ${zone_resp.data.id}

  - step: create_ph_node
    type: database_query
    query: |
      INSERT INTO nodes (uid, greenhouse_id, zone_id, type, name, config, lifecycle_state, created_at, updated_at)
      VALUES (
        'e2e-ph-node-${TIMESTAMP_S}',
        :gh_id,
        :zone_id,
        'ph_node',
        'e2e-ph-node',
        '{"gh_uid":"test","zone_uid":"test"}',
        'bound',
        NOW(), NOW()
      )
      RETURNING id, uid
    params:
      gh_id: ${gh_row.0.id}
      zone_id: ${zone_id}
    save: ph_node

  - step: create_ph_channels
    type: database_query
    query: |
      INSERT INTO node_channels (node_id, channel, type, metric, unit, config, is_active, created_at, updated_at)
      SELECT :node_id, ch, typ, met, unt, cfg::jsonb, TRUE, NOW(), NOW()
      FROM (VALUES
        ('ph_sensor', 'SENSOR', 'ph', 'pH', '{"actuator_type": null}'),
        ('pump_acid',  'ACTUATOR', 'pump', 'ml', '{"actuator_type": "PERISTALTIC_PUMP", "pump_calibration": {"component": "ph_down"}}'),
        ('pump_base',  'ACTUATOR', 'pump', 'ml', '{"actuator_type": "PERISTALTIC_PUMP", "pump_calibration": {"component": "ph_up"}}')
      ) AS t(ch, typ, met, unt, cfg)
      ON CONFLICT (node_id, channel) DO UPDATE
        SET type=EXCLUDED.type, metric=EXCLUDED.metric, config=EXCLUDED.config
    params:
      node_id: ${ph_node.0.id}
    save: _

  - step: get_channels
    type: database_query
    query: |
      SELECT id, channel FROM node_channels WHERE node_id = :node_id
    params:
      node_id: ${ph_node.0.id}
    save: channels

  - step: setup_pump_calibrations
    type: database_query
    query: |
      INSERT INTO pump_calibrations (node_channel_id, component, ml_per_sec, is_active, source, valid_from, created_at, updated_at)
      SELECT nc.id, nc.config->>'pump_calibration.component', 0.8, TRUE, 'e2e_test', NOW(), NOW(), NOW()
      FROM node_channels nc
      WHERE nc.node_id = :node_id AND nc.type = 'ACTUATOR'
      ON CONFLICT DO NOTHING
    params:
      node_id: ${ph_node.0.id}
    save: _

  - step: setup_infrastructure
    type: database_query
    query: |
      INSERT INTO infrastructure_instances (zone_id, instance_type, name, config, created_at, updated_at)
      VALUES (:zone_id, 'ph_dosing', 'e2e-ph-infra', '{}', NOW(), NOW())
      RETURNING id
    params:
      zone_id: ${zone_id}
    save: infra

  - step: bind_channels_to_infra
    type: database_query
    query: |
      INSERT INTO channel_bindings (infrastructure_instance_id, node_channel_id, direction, role, created_at, updated_at)
      SELECT :infra_id, nc.id,
             'actuator',
             CASE nc.config->>'pump_calibration.component'
               WHEN 'ph_down' THEN 'ph_acid_pump'
               WHEN 'ph_up'   THEN 'ph_base_pump'
             END,
             NOW(), NOW()
      FROM node_channels nc
      WHERE nc.node_id = :node_id AND nc.type = 'ACTUATOR'
    params:
      infra_id: ${infra.0.id}
      node_id: ${ph_node.0.id}
    save: _

  - step: create_plant_and_recipe
    type: api_post
    endpoint: /api/plants
    payload:
      name: e2e-ph-test-plant
      description: E2E pH PID Ki test
    save: plant_resp

  - step: create_recipe
    type: api_post
    endpoint: /api/recipes
    payload:
      name: e2e-ph-recipe
      plant_id: ${plant_resp.data.id}
    save: recipe_resp

  - step: create_recipe_phase
    type: api_post
    endpoint: /api/recipes/${recipe_resp.data.id}/phases
    payload:
      name: vegetative
      duration_days: 30
      ph_target: 5.80
      ph_min: 5.50
      ph_max: 6.10
      ec_target: 1.60
      ec_min: 1.20
      ec_max: 2.00
      order: 1
    save: _

  - step: start_grow_cycle
    type: api_post
    endpoint: /api/zones/${zone_id}/grow-cycles
    payload:
      recipe_revision_id: ${recipe_resp.data.latest_revision_id}
      started_at: ${NOW_ISO}
    save: cycle_resp

  - step: mark_test_start
    type: database_query
    query: "SELECT NOW() AS t"
    save: t_start
    expected_rows: 1

  - step: inject_ph_low
    type: database_query
    query: |
      INSERT INTO telemetry_last (sensor_id, last_value, updated_at)
      SELECT s.id, 5.50, NOW()
      FROM sensors s
      JOIN nodes n ON s.node_id = n.id
      WHERE n.id = :node_id AND s.metric = 'ph'
      ON CONFLICT (sensor_id) DO UPDATE
        SET last_value = 5.50, updated_at = NOW()
    params:
      node_id: ${ph_node.0.id}
    save: _

  - step: wait_for_correction_event
    type: db_wait
    timeout: 120s
    query: |
      SELECT id, payload
      FROM zone_events
      WHERE zone_id = :zone_id
        AND type = 'PH_CORRECTED'
        AND created_at > :since
      LIMIT 1
    params:
      zone_id: ${zone_id}
      since: ${t_start.0.t}
    save: correction_event
    expected_rows: 1

  - step: verify_correction_happened
    type: assert
    assert: ${correction_event.0.id} != ""
    error_message: "Ожидалось PH_CORRECTED событие, но оно не появилось за 120s"

  - step: verify_pid_integral_active
    type: database_query
    query: |
      SELECT integral, prev_error, current_zone
      FROM pid_state
      WHERE zone_id = :zone_id AND pid_type = 'ph'
    params:
      zone_id: ${zone_id}
    save: pid_state_row
    expected_rows: 1

  # integral != 0 означает что Ki сработал
  - step: verify_integral_nonzero
    type: assert
    assert: ${pid_state_row.0.integral} != 0.0
    error_message: "PID integral должен быть ненулевым после коррекции с Ki>0"
```

---

### Задача 3.5: E2E тест `E81_ec_correction_partial_calibration.yaml`

**Цель:** Подтвердить что EC-коррекция работает при частично заполненной `pump_calibrations`.

**Файл:** `tests/e2e/scenarios/automation_engine/E81_ec_correction_partial_calibration.yaml`

**Сценарий:**
1. Создать зону с 4 EC-насосами
2. Заполнить `pump_calibrations` только для npk и calcium (micro и magnesium без калибровки)
3. Установить EC_target=1.60, инжектировать EC=1.00 (большой deficit)
4. Ждать EC_DOSING события
5. Проверить что команды `run_pump(add_nutrients)` пришли для npk и calcium
6. Проверить что micro и magnesium НЕ получили команды

**Структура:** Аналогична E80, с теми же паттернами создания зоны/узлов/каналов.

Добавить проверку:
```yaml
  - step: verify_npk_commanded
    type: database_query
    query: |
      SELECT COUNT(*) AS cnt
      FROM command_tracking ct
      WHERE ct.zone_id = :zone_id
        AND ct.command->>'cmd' = 'run_pump'
        AND ct.command->'params'->>'component' = 'npk'
        AND ct.sent_at > :since
    params:
      zone_id: ${zone_id}
      since: ${t_start.0.t}
    save: npk_cmds

  - step: assert_npk_commanded
    type: assert
    assert: ${npk_cmds.0.cnt} > 0
    error_message: "NPK должен получить команду даже если micro/magnesium не откалиброваны"
```

---

### Критерии приёмки Агента 3

- [ ] `test_adaptive_pid.py` проходит полностью (`pytest test_adaptive_pid.py -v` — все зелёные)
- [ ] `test_relay_autotune.py` проходит (`pytest test_relay_autotune.py -v`)
- [ ] `test_correction_ec_batch_partial.py` проходит: `test_micro_missing_calibration_still_doses_others` → PASS
- [ ] `E80_ph_pid_ki_convergence.yaml` проходит в E2E окружении
- [ ] `E81_ec_correction_partial_calibration.yaml` проходит в E2E окружении
- [ ] `make test` — все тесты зелёные

---

## Порядок выполнения агентами

```
Агент 1 → независимо (только utils/ и services/)
Агент 2 → независимо (только correction_*.py)
    Агент 2 должен дождаться схему изменений AdaptivePidConfig от Агента 1
    или прочитать изменённый adaptive_pid.py перед написанием кода
Агент 3 → после Агента 1 и Агента 2
    Читает все изменённые файлы, пишет тесты к финальному состоянию
```

Если агенты запускаются параллельно — Агент 3 должен быть отложен.

---

## Схема БД (финальная)

### `pid_state` — добавить столбцы
```sql
ALTER TABLE pid_state
  ADD COLUMN last_dose_at TIMESTAMPTZ,         -- замена last_output_ms для wallclock
  ADD COLUMN prev_derivative DOUBLE PRECISION DEFAULT 0.0;  -- для восстановления фильтра D
-- last_output_ms оставить для обратной совместимости (не использовать)
```

### `zone_pid_configs` — добавить autotune_meta в JSONB
Структура `config` JSONB расширяется:
```json
{
  "setpoint": 5.80,
  "dead_zone": 0.05,
  "close_zone": 0.30,
  "zone_coeffs": {
    "close": {"kp": 5.0, "ki": 0.05, "kd": 0.0},
    "far":   {"kp": 8.0, "ki": 0.02, "kd": 0.0}
  },
  "max_output": 20.0,
  "min_interval_ms": 90000,
  "max_integral": 20.0,
  "autotune_meta": {               // новое поле, заполняется после relay autotune
    "source": "relay_autotune",
    "ku": 18.5,
    "tu_sec": 95.0,
    "tuned_at": "2026-03-05T12:00:00Z",
    "cycles_detected": 3
  }
}
```
Схема изменяется только через JSONB merge — никаких новых столбцов.

---

## Проверочный чеклист (финальный)

| # | Проверка | Метод |
|---|---------|-------|
| 1 | `KI_CLOSE > 0` для pH и EC | grep settings.py |
| 2 | integral ≠ 0 после 5 итераций с const error | unit test |
| 3 | relay autotune завершается за < 2ч на simulated plant | unit test |
| 4 | `correction_ec_batch` с micro ml_per_sec=0 → NPK/Ca/Mg дозируются | unit test |
| 5 | `get_dt_seconds` с raw_dt=600s → возвращает 300s | unit test |
| 6 | `restore_pid_state()` не блокирует при перезапуске через 30 сек | unit test |
| 7 | E80: PH_CORRECTED появляется в 120s при pH=5.50, target=5.80 | E2E |
| 8 | E81: NPK дозируется при micro без калибровки | E2E |
| 9 | `make test` — все зелёные | CI |
| 10 | PH_CORRECTED отображается в ZoneEventsTab с payload | frontend |
| 11 | PumpCalibrationsPanel сохраняет ml_per_sec в pump_calibrations | frontend + API |
| 12 | Кнопка "Запустить автотюнинг" вызывает AE endpoint | frontend + API |
| 13 | max_integral и min_interval (в минутах) редактируются в PidConfigForm | frontend |
| 14 | Смена PID конфига создаёт PID_CONFIG_UPDATED событие в zone_events | backend |

---

## Агент 4: Frontend — PID Advanced Panel + Zone Events

### Цель
Переработать отображение событий коррекции и расширить UI управления PID — калибровки насосов, relay autotune, правильные параметры формы.

### Документация для изучения
- `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md` — архитектура frontend
- `doc_ai/07_FRONTEND/FRONTEND_TESTING.md` — подход к тестированию

### Входные файлы (прочитать полностью)

| Файл | Строк | Что делает |
|------|-------|-----------|
| `backend/laravel/resources/js/utils/i18n.js` | ~200 | Переводы событий и classifyEventKind |
| `backend/laravel/resources/js/Components/PidConfigForm.vue` | 388 | Существующая форма PID |
| `backend/laravel/resources/js/types/PidConfig.ts` | 49 | TypeScript типы PID |
| `backend/laravel/resources/js/Pages/Zones/Tabs/ZoneEventsTab.vue` | ~300 | Таблица событий зоны |
| `backend/laravel/resources/js/Pages/Zones/Tabs/ZoneAutomationTab.vue` | ~500 | Вкладка автоматики |
| `backend/laravel/resources/js/composables/usePidConfig.ts` | ~100 | API composable для PID |

---

### Задача 4.1: Обновить `utils/i18n.js` — добавить события коррекции

**В функцию `classifyEventKind(kind)`** добавить ветки перед `return 'INFO'`:

```javascript
// Коррекционные ACTION-события
if (
  kind === 'PH_CORRECTED' || kind === 'EC_DOSING' ||
  kind === 'PUMP_DOSE_SENT' || kind === 'RELAY_AUTOTUNE_STARTED' ||
  kind === 'RELAY_AUTOTUNE_COMPLETE' || kind === 'PUMP_CALIBRATION_SAVED'
) return 'ACTION'

// Пропуски коррекции — INFO
if (
  kind === 'PID_OUTPUT' ||
  kind.startsWith('CORRECTION_SKIPPED_') ||
  kind === 'CORRECTION_STATE_TRANSITION' ||
  kind === 'PID_CONFIG_UPDATED'
) return 'INFO'

// Equipment warnings
if (
  kind === 'EQUIPMENT_ANOMALY_BLOCKED' || kind === 'EQUIPMENT_ANOMALY_RELEASED' ||
  kind === 'PUMP_CALIBRATION_STALE' || kind === 'RELAY_AUTOTUNE_TIMEOUT'
) return 'WARNING'
```

**В функцию `translateEventKind(kind)`** добавить переводы:

```javascript
// Коррекция pH/EC
'PH_CORRECTED':            'pH скорректирован',
'EC_DOSING':               'EC: подача питания',
'PUMP_DOSE_SENT':          'Доза отправлена насосу',
'PID_OUTPUT':              'PID: расчёт выхода',
'PID_CONFIG_UPDATED':      'Конфиг PID обновлён',
'CORRECTION_STATE_TRANSITION': 'Коррекция: переход состояния',

// Пропуски коррекции
'CORRECTION_SKIPPED_DEAD_ZONE':         'Коррекция: в мёртвой зоне',
'CORRECTION_SKIPPED_COOLDOWN':          'Коррекция: в паузе (кулдаун)',
'CORRECTION_SKIPPED_MISSING_ACTUATOR':  'Коррекция: нет насоса',
'CORRECTION_SKIPPED_NO_CALIBRATION':    'Коррекция: нет калибровки',
'CORRECTION_SKIPPED_WATER_LEVEL':       'Коррекция: мало воды',
'CORRECTION_SKIPPED_FRESHNESS':         'Коррекция: устаревшие данные',
'CORRECTION_SKIPPED_ANOMALY_BLOCK':     'Коррекция: аномалия оборудования',

// Автотюнинг
'RELAY_AUTOTUNE_STARTED':   'Relay-автотюнинг запущен',
'RELAY_AUTOTUNE_COMPLETE':  'Relay-автотюнинг завершён',
'RELAY_AUTOTUNE_TIMEOUT':   'Relay-автотюнинг: таймаут',

// Калибровки
'PUMP_CALIBRATION_SAVED':   'Калибровка насоса сохранена',
'PUMP_CALIBRATION_STALE':   'Калибровка насоса устарела',

// Equipment anomaly
'EQUIPMENT_ANOMALY_BLOCKED':  'Оборудование: блокировка (нет эффекта)',
'EQUIPMENT_ANOMALY_RELEASED': 'Оборудование: блокировка снята',
```

---

### Задача 4.2: Обновить `types/PidConfig.ts`

**Полная замена** содержимого файла:

```typescript
/**
 * Коэффициенты PID для одной зоны.
 */
export interface PidZoneCoeffs {
  kp: number
  ki: number
  kd: number
}

/**
 * PID конфигурация зоны (pH или EC).
 * Хранится в zone_pid_configs.config (JSONB).
 */
export interface PidConfig {
  target: number                   // Целевое значение (pH: 4-9, EC: 0-10)
  dead_zone: number                // Мёртвая зона (нет коррекции)
  close_zone: number               // Ближняя зона (close coeffs)
  far_zone: number                 // Дальняя зона (far coeffs)
  zone_coeffs: {
    close: PidZoneCoeffs
    far: PidZoneCoeffs
  }
  max_output: number               // Максимальная доза за раз (мл)
  min_interval_ms: number          // Минимальная пауза между дозами (мс)
  max_integral: number             // Ограничение интегральной суммы
  autotune_meta?: PidAutotuneMeta  // Результат последнего relay autotune
}

/**
 * Метаданные relay autotune после завершения.
 */
export interface PidAutotuneMeta {
  source: 'relay_autotune'
  ku: number               // Ultimate gain
  tu_sec: number           // Ultimate period (секунды)
  oscillation_amplitude: number
  cycles_detected: number
  tuned_at: string         // ISO datetime
}

/**
 * PID конфиг с метаданными из API.
 */
export interface PidConfigWithMeta {
  type: 'ph' | 'ec'
  config: PidConfig
  is_default?: boolean
  updated_at?: string
  updated_by?: number
}

/**
 * Лог PID вывода (из zone_events PID_OUTPUT / PID_CONFIG_UPDATED).
 */
export interface PidLog {
  id: number
  type: 'ph' | 'ec' | 'config_updated'
  zone_state?: 'dead' | 'close' | 'far'
  output?: number
  error?: number
  integral_term?: number    // НОВОЕ: значение интегральной части
  dt_seconds?: number
  current?: number
  target?: number
  safety_skip_reason?: string
  pid_type?: 'ph' | 'ec'
  old_config?: PidConfig
  new_config?: PidConfig
  updated_by?: number
  created_at: string
}

/**
 * Калибровка одного дозирующего насоса.
 */
export interface PumpCalibration {
  node_channel_id: number
  role: string              // 'ph_acid_pump' | 'ph_base_pump' | 'ec_npk_pump' | ...
  component: string         // 'ph_down' | 'ph_up' | 'npk' | 'calcium' | 'magnesium' | 'micro'
  channel_label: string     // Человекочитаемое название
  node_uid: string
  channel: string
  ml_per_sec: number | null // null = не откалиброван
  k_ms_per_ml_l: number | null
  source: string | null     // 'manual' | 'relay_autotune' | 'legacy_config_fallback'
  valid_from: string | null // ISO datetime
  is_active: boolean
  calibration_age_days?: number
}

/**
 * Статус relay autotune для зоны.
 */
export interface RelayAutotuneStatus {
  zone_id: number
  pid_type: 'ph' | 'ec'
  status: 'idle' | 'running' | 'complete' | 'timeout'
  started_at?: string
  completed_at?: string
  result?: PidAutotuneMeta
  progress?: {
    cycles_detected: number
    min_cycles: number
    elapsed_sec: number
    max_duration_sec: number
  }
}
```

---

### Задача 4.3: Переработать `Components/PidConfigForm.vue`

**Что изменить:**

1. **Убрать** поля `adaptation_rate` и `enable_autotune` checkbox (старый autotune удалён)
2. **Добавить** поле `max_integral` (лимит интегральной суммы)
3. **Изменить** отображение `min_interval_ms` — показывать в **минутах** (конвертация: `ms / 60000`), сохранять в ms
4. **Обновить** дефолтные значения формы под новые параметры из Агента 1

**Структура после изменений:**

```vue
<template>
  <Card>
    <!-- Переключатель pH / EC — оставить без изменений -->

    <form @submit.prevent="onSubmit" class="space-y-4">
      <!-- Секция: Основные параметры -->
      <div class="grid grid-cols-2 gap-4">
        <!-- target (оставить) -->
        <!-- dead_zone (оставить) -->
        <!-- close_zone (оставить) -->
        <!-- far_zone (оставить) -->
      </div>

      <!-- Секция: Коэффициенты CLOSE (оставить) -->
      <!-- Секция: Коэффициенты FAR (оставить) -->

      <!-- Секция: Дозирование и паузы — ОБНОВИТЬ -->
      <div class="grid grid-cols-2 gap-4 border-t pt-4">
        <div>
          <label>Максимальная доза (мл)</label>
          <input v-model.number="form.max_output" type="number" step="0.1" min="0.1" max="500" />
          <p class="hint">pH: 20 мл, EC: 50 мл — рекомендуемые значения</p>
        </div>
        <div>
          <label>Пауза между дозами (мин)</label>
          <!-- Отображаем в минутах, храним в ms: intervalMinutes = min_interval_ms / 60000 -->
          <input v-model.number="intervalMinutes" type="number" step="0.5" min="0.5" max="60" />
          <p class="hint">pH: 1.5 мин, EC: 2 мин — рекомендуемые значения</p>
        </div>
        <div>
          <label>Лимит интеграла (max_integral)</label>
          <input v-model.number="form.max_integral" type="number" step="1" min="1" max="500" />
          <p class="hint">Ограничивает накопление интегральной ошибки. pH: 20, EC: 100</p>
        </div>
      </div>

      <!-- Safeguard warning (обновить условие: убрать autotune) -->
      <!-- needsConfirmation: kp > 200 или min_interval_ms < 30_000 -->

      <!-- Кнопки (оставить) -->
    </form>
  </Card>
</template>

<script setup lang="ts">
// Добавить computed:
const intervalMinutes = computed({
  get: () => form.value.min_interval_ms / 60000,
  set: (val: number) => { form.value.min_interval_ms = Math.round(val * 60000) },
})

// Обновить defaults:
const DEFAULT_CONFIGS = {
  ph: {
    target: 5.8, dead_zone: 0.05, close_zone: 0.30, far_zone: 1.0,
    zone_coeffs: { close: {kp:5.0, ki:0.05, kd:0}, far: {kp:8.0, ki:0.02, kd:0} },
    max_output: 20.0, min_interval_ms: 90_000, max_integral: 20.0,
  },
  ec: {
    target: 1.6, dead_zone: 0.10, close_zone: 0.50, far_zone: 1.5,
    zone_coeffs: { close: {kp:30.0, ki:0.30, kd:0}, far: {kp:50.0, ki:0.10, kd:0} },
    max_output: 50.0, min_interval_ms: 120_000, max_integral: 100.0,
  },
}
// Использовать при loadConfig → если is_default: true
</script>
```

---

### Задача 4.4: Создать `Components/PumpCalibrationsPanel.vue`

**Новый компонент** — панель калибровки дозирующих насосов.

**Структура:**

```vue
<template>
  <Card>
    <div class="flex items-center justify-between mb-4">
      <div class="text-sm font-semibold">Калибровки насосов</div>
      <Badge v-if="hasUncalibrated" variant="warning">
        {{ uncalibratedCount }} без калибровки
      </Badge>
    </div>

    <!-- Список насосов -->
    <div v-if="loading" class="text-sm text-muted">Загрузка...</div>
    <div v-else-if="calibrations.length === 0" class="text-sm text-muted">
      Дозирующие насосы не найдены. Подключите узлы к зоне.
    </div>
    <div v-else class="space-y-3">
      <div
        v-for="pump in calibrations"
        :key="pump.node_channel_id"
        class="border rounded-md p-3"
      >
        <!-- Заголовок строки насоса -->
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <!-- Иконка в зависимости от роли -->
            <RoleIcon :role="pump.role" class="w-4 h-4 text-muted" />
            <span class="text-sm font-medium">{{ formatPumpLabel(pump) }}</span>
            <Badge
              :variant="pump.ml_per_sec ? 'success' : 'warning'"
              class="text-xs"
            >
              {{ pump.ml_per_sec ? `${pump.ml_per_sec} мл/с` : 'Не откалиброван' }}
            </Badge>
          </div>
          <!-- Источник калибровки -->
          <span class="text-xs text-muted">
            {{ formatCalibrationSource(pump.source, pump.valid_from) }}
          </span>
        </div>

        <!-- Поле редактирования ml_per_sec -->
        <div class="flex items-center gap-2">
          <input
            :value="editValues[pump.node_channel_id]"
            type="number"
            step="0.01"
            min="0.01"
            max="20"
            placeholder="мл/сек"
            class="input-field w-28 text-sm"
            @input="editValues[pump.node_channel_id] = parseFloat($event.target.value)"
          />
          <span class="text-xs text-muted">мл/с</span>
          <Button
            size="xs"
            :disabled="saving[pump.node_channel_id]"
            @click="savePumpCalibration(pump)"
          >
            {{ saving[pump.node_channel_id] ? 'Сохранение...' : 'Сохранить' }}
          </Button>
        </div>

        <!-- Устаревшее предупреждение -->
        <div v-if="pump.calibration_age_days && pump.calibration_age_days > 30" class="mt-1">
          <span class="text-xs text-[color:var(--badge-warning-text)]">
            Калибровка устарела ({{ pump.calibration_age_days }} дн)
          </span>
        </div>
      </div>
    </div>

    <!-- Дефолтные значения подсказка -->
    <div class="mt-3 p-2 rounded bg-[color:var(--bg-surface-strong)] text-xs text-muted">
      <strong>Рекомендуемые значения:</strong>
      pH кислота/щёлочь: 0.5–1.0 мл/с · NPK: 0.8–1.5 мл/с · Ca/Mg/Micro: 0.6–1.0 мл/с
    </div>
  </Card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { PumpCalibration } from '@/types/PidConfig'

const props = defineProps<{ zoneId: number }>()

const calibrations = ref<PumpCalibration[]>([])
const loading = ref(true)
const editValues = ref<Record<number, number>>({})
const saving = ref<Record<number, boolean>>({})

const hasUncalibrated = computed(() => calibrations.value.some(p => !p.ml_per_sec))
const uncalibratedCount = computed(() => calibrations.value.filter(p => !p.ml_per_sec).length)

async function loadCalibrations() {
  loading.value = true
  try {
    const resp = await fetch(`/api/zones/${props.zoneId}/pump-calibrations`)
    const data = await resp.json()
    calibrations.value = data.data ?? []
    // Заполнить editValues из текущих калибровок
    for (const pump of calibrations.value) {
      editValues.value[pump.node_channel_id] = pump.ml_per_sec ?? getDefaultMlPerSec(pump.component)
    }
  } finally {
    loading.value = false
  }
}

async function savePumpCalibration(pump: PumpCalibration) {
  const mlPerSec = editValues.value[pump.node_channel_id]
  if (!mlPerSec || mlPerSec <= 0) return
  saving.value[pump.node_channel_id] = true
  try {
    await fetch(`/api/zones/${props.zoneId}/pump-calibrations/${pump.node_channel_id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': getCsrfToken() },
      body: JSON.stringify({ ml_per_sec: mlPerSec }),
    })
    await loadCalibrations() // перезагрузить
  } finally {
    saving.value[pump.node_channel_id] = false
  }
}

function getDefaultMlPerSec(component: string): number {
  const defaults: Record<string, number> = {
    ph_down: 0.5, ph_up: 0.5,
    npk: 1.0, calcium: 0.8, magnesium: 0.8, micro: 0.7,
  }
  return defaults[component] ?? 1.0
}

function formatPumpLabel(pump: PumpCalibration): string {
  const labels: Record<string, string> = {
    ph_acid_pump: 'pH Down (кислота)',
    ph_base_pump: 'pH Up (щёлочь)',
    ec_npk_pump: 'NPK (питательный)',
    ec_calcium_pump: 'Кальций (Ca)',
    ec_magnesium_pump: 'Магний (Mg)',
    ec_micro_pump: 'Микроэлементы',
  }
  return labels[pump.role] ?? pump.channel_label
}

function formatCalibrationSource(source: string | null, validFrom: string | null): string {
  if (!source || !validFrom) return 'Не задана'
  const date = new Date(validFrom).toLocaleDateString('ru-RU')
  if (source === 'relay_autotune') return `Автотюнинг (${date})`
  if (source === 'manual') return `Вручную (${date})`
  return date
}

onMounted(() => loadCalibrations())
</script>
```

---

### Задача 4.5: Создать `Components/RelayAutotuneTrigger.vue`

**Новый компонент** — кнопка запуска и статус relay autotune.

```vue
<template>
  <Card>
    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <div class="text-sm font-semibold">Relay Автотюнинг</div>
        <!-- Переключатель pH / EC -->
        <div class="flex gap-1">
          <Button size="xs" :variant="selectedType === 'ph' ? 'default' : 'outline'" @click="selectedType = 'ph'">pH</Button>
          <Button size="xs" :variant="selectedType === 'ec' ? 'default' : 'outline'" @click="selectedType = 'ec'">EC</Button>
        </div>
      </div>

      <!-- Статус autotune -->
      <div class="text-xs space-y-1">
        <div v-if="status?.status === 'running'" class="flex items-center gap-2 text-[color:var(--badge-info-text)]">
          <span class="animate-pulse">●</span>
          <span>
            Выполняется: {{ status.progress?.cycles_detected ?? 0 }}/{{ status.progress?.min_cycles ?? 3 }} циклов
            ({{ formatElapsed(status.progress?.elapsed_sec) }})
          </span>
        </div>
        <div v-else-if="status?.status === 'complete'" class="text-[color:var(--badge-success-text)]">
          ✓ Завершён: Kp={{ status.result?.ku ? (0.45 * status.result.ku).toFixed(3) : '?' }},
          Ki={{ status.result?.tu_sec ? (0.45 * (status.result?.ku ?? 0) / (0.83 * status.result.tu_sec)).toFixed(4) : '?' }}
          ({{ status.completed_at ? new Date(status.completed_at).toLocaleString('ru-RU') : '' }})
        </div>
        <div v-else-if="status?.status === 'timeout'" class="text-[color:var(--badge-warning-text)]">
          Таймаут — система не вошла в колебания. Проверьте настройки амплитуды.
        </div>
        <div v-else class="text-muted">
          Не запускался
        </div>
      </div>

      <!-- Описание -->
      <div class="text-xs text-muted bg-[color:var(--bg-surface-strong)] p-2 rounded">
        Relay-автотюнинг занимает <strong>1–2 часа</strong>. Во время процедуры система
        использует on/off управление вместо PID. Результат (Kp, Ki) автоматически
        сохраняется в настройках PID.
      </div>

      <!-- Кнопка запуска -->
      <Button
        size="sm"
        :disabled="isRunning || starting"
        variant="outline"
        @click="startAutotune"
      >
        <span v-if="starting">Запуск...</span>
        <span v-else-if="isRunning">Выполняется ({{ status?.progress?.cycles_detected }}/3 циклов)</span>
        <span v-else>Запустить автотюнинг {{ selectedType.toUpperCase() }}</span>
      </Button>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { RelayAutotuneStatus } from '@/types/PidConfig'

const props = defineProps<{ zoneId: number }>()
const selectedType = ref<'ph' | 'ec'>('ph')
const status = ref<RelayAutotuneStatus | null>(null)
const starting = ref(false)
let pollInterval: ReturnType<typeof setInterval> | null = null

const isRunning = computed(() => status.value?.status === 'running')

async function loadStatus() {
  try {
    const resp = await fetch(`/api/zones/${props.zoneId}/relay-autotune/status?pid_type=${selectedType.value}`)
    const data = await resp.json()
    status.value = data.data ?? null
  } catch {}
}

async function startAutotune() {
  starting.value = true
  try {
    await fetch(`/api/zones/${props.zoneId}/relay-autotune`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': getCsrfToken() },
      body: JSON.stringify({ pid_type: selectedType.value }),
    })
    await loadStatus()
    // Начать polling каждые 10 секунд
    pollInterval = setInterval(loadStatus, 10_000)
  } finally {
    starting.value = false
  }
}

function formatElapsed(sec?: number): string {
  if (!sec) return '0 мин'
  return `${Math.round(sec / 60)} мин`
}

onMounted(() => loadStatus())
onUnmounted(() => { if (pollInterval) clearInterval(pollInterval) })
</script>
```

---

### Задача 4.6: Обновить `ZoneAutomationTab.vue` — добавить новые компоненты

Найти место где используется `PidConfigForm` в `ZoneAutomationTab.vue` и добавить рядом:

```vue
<!-- Существующий PidConfigForm — оставить -->
<PidConfigForm :zone-id="zoneId" @saved="onPidSaved" />

<!-- НОВОЕ: Калибровки насосов — сразу после PidConfigForm -->
<PumpCalibrationsPanel :zone-id="zoneId" class="mt-4" />

<!-- НОВОЕ: Relay Autotune — после калибровок -->
<RelayAutotuneTrigger :zone-id="zoneId" class="mt-4" />
```

Добавить импорты:
```typescript
import PumpCalibrationsPanel from '@/Components/PumpCalibrationsPanel.vue'
import RelayAutotuneTrigger from '@/Components/RelayAutotuneTrigger.vue'
```

---

### Задача 4.7: Обновить `ZoneEventsTab.vue` — показывать payload коррекций

**Существующий компонент** показывает только `event.message`. Добавить expandable payload для событий коррекции.

Найти строку рендера события в VirtualList и добавить:

```vue
<!-- Внутри строки события (после message) -->
<template v-if="hasCorrectionPayload(event)">
  <!-- Кнопка разворота -->
  <button
    class="text-xs text-[color:var(--text-muted)] underline ml-2"
    @click="toggleExpanded(event.id)"
  >
    {{ expandedIds.has(event.id) ? 'Скрыть' : 'Подробности' }}
  </button>

  <!-- Payload панель -->
  <div
    v-if="expandedIds.has(event.id)"
    class="mt-1 p-2 rounded bg-[color:var(--bg-surface-strong)] text-xs font-mono space-y-0.5"
  >
    <template v-if="event.payload?.output !== undefined">
      <div>Доза: <strong>{{ event.payload.output }} мл</strong></div>
    </template>
    <template v-if="event.payload?.error !== undefined">
      <div>Ошибка: <strong>{{ event.payload.error?.toFixed(3) }}</strong></div>
    </template>
    <template v-if="event.payload?.current !== undefined">
      <div>Текущее: <strong>{{ event.payload.current }}</strong> → Цель: <strong>{{ event.payload.target }}</strong></div>
    </template>
    <template v-if="event.payload?.zone_state">
      <div>Зона PID: <strong>{{ event.payload.zone_state }}</strong></div>
    </template>
    <template v-if="event.payload?.integral_term !== undefined">
      <div>Интеграл: <strong>{{ event.payload.integral_term?.toFixed(4) }}</strong></div>
    </template>
    <template v-if="event.payload?.component">
      <div>Компонент: <strong>{{ event.payload.component }}</strong></div>
    </template>
    <template v-if="event.payload?.reason">
      <div>Причина пропуска: <strong>{{ event.payload.reason }}</strong></div>
    </template>
  </div>
</template>
```

Добавить в `<script setup>`:
```typescript
const CORRECTION_EVENT_KINDS = new Set([
  'PH_CORRECTED', 'EC_DOSING', 'PID_OUTPUT',
  'CORRECTION_SKIPPED_DEAD_ZONE', 'CORRECTION_SKIPPED_COOLDOWN',
  'CORRECTION_SKIPPED_MISSING_ACTUATOR', 'CORRECTION_SKIPPED_NO_CALIBRATION',
  'RELAY_AUTOTUNE_COMPLETE', 'PUMP_CALIBRATION_SAVED',
])

function hasCorrectionPayload(event: ZoneEvent): boolean {
  return CORRECTION_EVENT_KINDS.has(event.kind) && !!event.payload
}

const expandedIds = ref<Set<number>>(new Set())
function toggleExpanded(id: number) {
  if (expandedIds.value.has(id)) expandedIds.value.delete(id)
  else expandedIds.value.add(id)
}
```

Обновить тип `ZoneEvent` в `types/ZoneEvent.ts` — добавить поле `payload?: Record<string, unknown>`.

---

### Задача 4.8: Backend API — Laravel контроллер калибровок

**Создать** `app/Http/Controllers/ZonePumpCalibrationsController.php`:

```php
class ZonePumpCalibrationsController extends Controller
{
    /**
     * GET /api/zones/{zone}/pump-calibrations
     * Список всех дозирующих насосов зоны с текущими калибровками.
     */
    public function index(Zone $zone): JsonResponse
    {
        // 1. Получить все каналы типа ACTUATOR в зоне через channel_bindings
        // JOIN: infrastructure_instances → channel_bindings → node_channels → nodes
        // WHERE: infrastructure_instances.zone_id = $zone->id
        //        AND channel_bindings.direction = 'actuator'
        //        AND channel_bindings.role IN ('ph_acid_pump', 'ph_base_pump', 'ec_npk_pump', ...)
        // LATERAL JOIN pump_calibrations (последняя активная)

        $pumps = DB::select("
            SELECT
                nc.id AS node_channel_id,
                cb.role,
                n.uid AS node_uid,
                nc.channel,
                nc.config->>'pump_calibration.component' AS component,
                pc.ml_per_sec,
                pc.k_ms_per_ml_l,
                pc.source,
                pc.valid_from,
                pc.is_active,
                EXTRACT(DAY FROM NOW() - pc.valid_from)::int AS calibration_age_days
            FROM infrastructure_instances ii
            JOIN channel_bindings cb ON cb.infrastructure_instance_id = ii.id
            JOIN node_channels nc ON nc.id = cb.node_channel_id
            JOIN nodes n ON n.id = nc.node_id
            LEFT JOIN LATERAL (
                SELECT ml_per_sec, k_ms_per_ml_l, source, valid_from, is_active
                FROM pump_calibrations
                WHERE node_channel_id = nc.id AND is_active = TRUE
                ORDER BY valid_from DESC LIMIT 1
            ) pc ON TRUE
            WHERE ii.zone_id = ?
              AND cb.direction = 'actuator'
              AND cb.role IN (
                'ph_acid_pump','ph_base_pump',
                'ec_npk_pump','ec_calcium_pump','ec_magnesium_pump','ec_micro_pump'
              )
            ORDER BY cb.role
        ", [$zone->id]);

        // Добавить channel_label из config
        $result = collect($pumps)->map(fn($p) => [
            'node_channel_id'     => $p->node_channel_id,
            'role'                => $p->role,
            'node_uid'            => $p->node_uid,
            'channel'             => $p->channel,
            'component'           => $p->component,
            'channel_label'       => $p->channel,
            'ml_per_sec'          => $p->ml_per_sec,
            'k_ms_per_ml_l'       => $p->k_ms_per_ml_l,
            'source'              => $p->source,
            'valid_from'          => $p->valid_from,
            'is_active'           => (bool)$p->is_active,
            'calibration_age_days'=> $p->calibration_age_days,
        ]);

        return response()->json(['status' => 'ok', 'data' => $result]);
    }

    /**
     * PUT /api/zones/{zone}/pump-calibrations/{channelId}
     * Обновить ml_per_sec для насоса. Создаёт новую запись в pump_calibrations.
     */
    public function update(Request $request, Zone $zone, int $channelId): JsonResponse
    {
        $data = $request->validate([
            'ml_per_sec'     => ['required', 'numeric', 'min:0.01', 'max:20'],
            'k_ms_per_ml_l'  => ['nullable', 'numeric', 'min:0'],
        ]);

        // Проверить что channel принадлежит зоне
        $binding = DB::table('channel_bindings as cb')
            ->join('infrastructure_instances as ii', 'ii.id', '=', 'cb.infrastructure_instance_id')
            ->where('ii.zone_id', $zone->id)
            ->where('cb.node_channel_id', $channelId)
            ->first();

        abort_if(!$binding, 404, 'Channel not bound to this zone');

        // Деактивировать старые калибровки
        DB::table('pump_calibrations')
            ->where('node_channel_id', $channelId)
            ->where('is_active', true)
            ->update(['is_active' => false, 'valid_to' => now()]);

        // Создать новую калибровку
        $component = DB::table('node_channels')
            ->where('id', $channelId)
            ->value(DB::raw("config->>'pump_calibration.component'"));

        DB::table('pump_calibrations')->insert([
            'node_channel_id' => $channelId,
            'component'       => $component ?? 'unknown',
            'ml_per_sec'      => $data['ml_per_sec'],
            'k_ms_per_ml_l'   => $data['k_ms_per_ml_l'] ?? null,
            'source'          => 'manual',
            'is_active'       => true,
            'valid_from'      => now(),
            'created_at'      => now(),
            'updated_at'      => now(),
        ]);

        // Создать zone_event
        $zone->events()->create([
            'type'    => 'PUMP_CALIBRATION_SAVED',
            'details' => json_encode([
                'node_channel_id' => $channelId,
                'role'            => $binding->role,
                'ml_per_sec'      => $data['ml_per_sec'],
                'source'          => 'manual',
            ]),
        ]);

        return response()->json(['status' => 'ok']);
    }
}
```

**Добавить маршруты** в `routes/web.php` (в группу authenticated):
```php
Route::get('/api/zones/{zone}/pump-calibrations', [ZonePumpCalibrationsController::class, 'index']);
Route::put('/api/zones/{zone}/pump-calibrations/{channelId}', [ZonePumpCalibrationsController::class, 'update']);
```

---

### Задача 4.9: Backend API — Relay Autotune endpoints (Laravel → AE proxy)

**Создать** `app/Http/Controllers/ZoneRelayAutotuneController.php`:

```php
class ZoneRelayAutotuneController extends Controller
{
    /**
     * POST /api/zones/{zone}/relay-autotune
     * Запустить relay autotune на AE.
     */
    public function start(Request $request, Zone $zone): JsonResponse
    {
        $data = $request->validate([
            'pid_type' => ['required', Rule::in(['ph', 'ec'])],
        ]);

        // Проверить что цикл активен
        abort_if(!$zone->activeGrowCycle, 422, 'No active grow cycle in zone');

        // Проксировать запрос к AE
        $aeUrl = config('services.automation_engine.url');
        $response = Http::post("{$aeUrl}/zones/{$zone->id}/start-relay-autotune", [
            'pid_type' => $data['pid_type'],
        ]);

        if (!$response->successful()) {
            return response()->json(['status' => 'error', 'message' => $response->json('detail')], 422);
        }

        // Создать zone_event
        $zone->events()->create([
            'type'    => 'RELAY_AUTOTUNE_STARTED',
            'details' => json_encode(['pid_type' => $data['pid_type']]),
        ]);

        return response()->json(['status' => 'ok', 'data' => $response->json()]);
    }

    /**
     * GET /api/zones/{zone}/relay-autotune/status
     * Получить статус autotune от AE.
     */
    public function status(Request $request, Zone $zone): JsonResponse
    {
        $pidType = $request->query('pid_type', 'ph');
        $aeUrl = config('services.automation_engine.url');

        $response = Http::get("{$aeUrl}/zones/{$zone->id}/relay-autotune/status", [
            'pid_type' => $pidType,
        ]);

        if (!$response->successful()) {
            return response()->json(['status' => 'ok', 'data' => ['status' => 'idle']]);
        }

        return response()->json(['status' => 'ok', 'data' => $response->json()]);
    }
}
```

**Маршруты:**
```php
Route::post('/api/zones/{zone}/relay-autotune', [ZoneRelayAutotuneController::class, 'start']);
Route::get('/api/zones/{zone}/relay-autotune/status', [ZoneRelayAutotuneController::class, 'status']);
```

---

### Задача 4.10: AE — создавать zone_events при коррекции

**Агент 4 должен проверить** что Python AE уже создаёт `zone_events` при каждой коррекции. Если нет — добавить в `correction_controller_apply.py` вызов:

```python
# После успешной отправки команды (apply_correction_with_events):
await create_zone_event(
    zone_id=zone_id,
    event_type="PH_CORRECTED",  # или EC_DOSING
    details={
        "output": round(output_ml, 3),
        "error": round(error, 4),
        "current": round(current_value, 3),
        "target": round(target, 3),
        "zone_state": zone_state,
        "integral_term": round(integral_term, 4),
        "correction_type": correction_type,  # 'add_acid' | 'add_base' | 'add_nutrients'
    },
)
```

Также создавать события для пропусков в `correction_controller_check_core.py`:

```python
# Для каждого gate (dead zone, cooldown, missing actuator, etc.)
# Использовать тип 'CORRECTION_SKIPPED_{REASON}' вместо общего INFO
# Например:
await create_zone_event(zone_id, "CORRECTION_SKIPPED_DEAD_ZONE", {
    "error": round(error, 4),
    "dead_zone": dead_zone_config,
    "current": current_value,
    "target": target,
})
```

Это обеспечит что **все действия AE отображаются в zone_events** на фронтенде.

---

### Задача 4.11: Передавать payload событий в Inertia props

**В `routes/web.php`** где формируется массив событий для `Zones/Show`:

Текущий код передаёт только `id, kind, message, occurred_at`. Добавить `payload`:

```php
$events = $eventsRaw->map(function ($event) use ($eventMessageFormatter) {
    // Извлечь payload из details JSON
    $details = [];
    if ($event->details) {
        $decoded = json_decode($event->details, true);
        if (is_array($decoded)) {
            $details = $decoded;
        }
    }

    return [
        'id'          => $event->id,
        'kind'        => $event->type ?? 'INFO',
        'message'     => $eventMessageFormatter->format($event),
        'occurred_at' => $event->created_at?->toIso8601String(),
        'payload'     => $details,  // НОВОЕ: передавать payload
    ];
});
```

Также обновить formatter `ZoneEventMessageFormatter` — добавить форматирование для новых событий:

```php
'PH_CORRECTED' => fn($d) => sprintf(
    'pH скорректирован: %.2f → %.2f, доза %.1f мл (%s)',
    $d['current'] ?? 0, $d['target'] ?? 0, $d['output'] ?? 0, $d['correction_type'] ?? ''
),
'EC_DOSING' => fn($d) => sprintf(
    'EC подача: %.2f → %.2f, доза %.1f мл',
    $d['current'] ?? 0, $d['target'] ?? 0, $d['output'] ?? 0
),
'CORRECTION_SKIPPED_DEAD_ZONE' => fn($d) => sprintf(
    'Коррекция пропущена (мёртвая зона): ошибка %.3f',
    $d['error'] ?? 0
),
'CORRECTION_SKIPPED_COOLDOWN' => fn($d) => 'Коррекция пропущена: кулдаун активен',
'RELAY_AUTOTUNE_COMPLETE' => fn($d) => sprintf(
    'Автотюнинг завершён: Kp=%.3f, Ki=%.4f (%d циклов)',
    $d['kp'] ?? 0, $d['ki'] ?? 0, $d['cycles_detected'] ?? 0
),
'PUMP_CALIBRATION_SAVED' => fn($d) => sprintf(
    'Калибровка насоса [%s]: %.2f мл/с',
    $d['role'] ?? '', $d['ml_per_sec'] ?? 0
),
```

---

### Критерии приёмки Агента 4

- [ ] В `ZoneEventsTab` события `PH_CORRECTED` и `EC_DOSING` отображаются с цветом ACTION (не INFO)
- [ ] При клике "Подробности" показывается payload (current, target, output, zone_state)
- [ ] `PumpCalibrationsPanel` отображает все дозирующие насосы зоны
- [ ] После сохранения ml_per_sec создаётся `PUMP_CALIBRATION_SAVED` событие в zone_events
- [ ] `RelayAutotuneTrigger` отображает статус autotune, кнопка вызывает API
- [ ] `GET /api/zones/{id}/pump-calibrations` возвращает список насосов с калибровками
- [ ] `PUT /api/zones/{id}/pump-calibrations/{channelId}` сохраняет новую калибровку
- [ ] `PidConfigForm` не имеет полей `adaptation_rate`, `enable_autotune`; имеет `max_integral`
- [ ] `min_interval_ms` отображается в минутах (90000ms = 1.5 мин)
- [ ] TypeScript: `npm run typecheck` проходит без ошибок

---

## Порядок выполнения (обновлённый)

```
Агент 1 (PID Engine Python)    ─┐
Агент 2 (Correction Flow)      ─┤→ независимы, можно параллельно
Агент 4 (Frontend + API)       ─┘  (Агент 4 не зависит от 1 и 2 в части API)

Агент 3 (Тесты) → после 1, 2, 4
```

**Важно для Агента 4:** при написании `ZoneEventsTab` expandable payload — Агент 4 должен обновить тип `ZoneEvent` в `types/ZoneEvent.ts` чтобы добавить `payload?: Record<string, unknown>`. Это необходимо для TypeScript компиляции.
