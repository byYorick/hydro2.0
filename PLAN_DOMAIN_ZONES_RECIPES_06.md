# План доработок: 06_DOMAIN_ZONES_RECIPES
# Приведение проекта в соответствие с документацией

## Дата создания: 2025-01-18
## Дата обновления: 2025-01-18 (после проверки кода)

---

## ОБЩИЕ ПРИНЦИПЫ

1. **Ничего не удалять** - только добавлять и улучшать
2. **Документация - эталон** - код должен соответствовать документации
3. **Обратная совместимость** - изменения не должны ломать существующий функционал
4. **Поэтапная реализация** - сначала критичные функции, потом остальные

---

## ТЕКУЩЕЕ СОСТОЯНИЕ

### ✅ Уже реализовано:
- ✅ Zone Controllers (Climate, Light, Irrigation, Health Monitor)
- ✅ Water Flow Engine (основная функциональность)
- ✅ ZoneHealthMonitor
- ✅ Events Engine (почти все типы)
- ✅ Alerts Engine
- ✅ Расчет объема полива
- ✅ Правильный порядок выполнения контроллеров

### ⚠️ Требует доработки:
- ⚠️ Интеграция защиты от сухого хода в scheduler
- ⚠️ Режимы Fill/Drain
- ⚠️ Рециркуляция
- ⚠️ API endpoint `next_phase`
- ⚠️ Расчет прогресса фазы

---

## ЭТАП 1: КРИТИЧЕСКИЕ ДОРАБОТКИ (Безопасность)

### 1.1. Интеграция защиты от сухого хода в scheduler

**Задача:** Интегрировать функцию `check_dry_run_protection()` в scheduler для автоматической остановки насоса при обнаружении сухого хода.

**Текущее состояние:**
- ✅ Функция `check_dry_run_protection()` реализована в `water_flow.py`
- ✅ Создает событие NO_FLOW
- ❌ НЕ интегрирована в scheduler для автоматической остановки насоса

**Шаги:**
1. Доработать `scheduler/main.py` в функции `execute_irrigation_schedule()`:
   - После запуска насоса запустить асинхронную задачу мониторинга
   - Через 3 секунды проверить flow через `check_dry_run_protection()`
   - Если обнаружен сухой ход - отправить команду остановки насоса
   - Создать событие PUMP_STOPPED с причиной "dry_run_detected"

2. Добавить команду остановки насоса:
   - Команда `{"cmd": "stop"}` для узла irrigation
   - Отправка через MQTT

**Файлы для изменения:**
- `backend/services/scheduler/main.py`
- `backend/services/common/water_flow.py` (возможно, добавить функцию остановки насоса)

**Оценка времени:** 2-3 часа

---

### 1.2. Режим наполнения (Fill Mode)

**Задача:** Реализовать режим наполнения согласно `WATER_FLOW_ENGINE.md` раздел 9

**Шаги:**
1. Добавить функцию в `water_flow.py`:
   ```python
   async def execute_fill_mode(zone_id: int, target_level: float, mqtt: MqttClient, gh_uid: str) -> bool
   ```
   - Логика: включить клапан подачи и насос
   - Мониторинг уровня воды
   - Остановка при достижении `target_level`
   - Создание событий FILL_STARTED, FILL_FINISHED

2. Добавить API endpoint в Laravel:
   - `POST /api/zones/{id}/fill`
   - Параметры: `{"target_level": 0.9}`
   - Валидация: `target_level` должен быть в диапазоне 0.1-1.0

3. Добавить обработку команды в `automation-engine`:
   - Создать функцию для обработки команды fill
   - Интеграция с MQTT для отправки команды узлу

**Файлы для изменения:**
- `backend/services/common/water_flow.py`
- `backend/services/automation-engine/main.py` (или создать отдельный модуль)
- `backend/laravel/app/Http/Controllers/ZoneController.php`
- `backend/laravel/routes/api.php`

**Оценка времени:** 4-6 часов

---

### 1.3. Режим слива (Drain Mode)

**Задача:** Реализовать режим слива согласно `WATER_FLOW_ENGINE.md` раздел 10

**Шаги:**
1. Добавить функцию в `water_flow.py`:
   ```python
   async def execute_drain_mode(zone_id: int, target_level: float, mqtt: MqttClient, gh_uid: str) -> bool
   ```
   - Логика: включить сливной насос/клапан
   - Мониторинг уровня воды
   - Остановка при достижении `target_level`
   - Создание событий DRAIN_STARTED, DRAIN_FINISHED

2. Добавить API endpoint в Laravel:
   - `POST /api/zones/{id}/drain`
   - Параметры: `{"target_level": 0.1}`
   - Валидация: `target_level` должен быть в диапазоне 0.0-0.9

3. Добавить обработку команды в `automation-engine`

**Файлы для изменения:**
- `backend/services/common/water_flow.py`
- `backend/services/automation-engine/main.py`
- `backend/laravel/app/Http/Controllers/ZoneController.php`
- `backend/laravel/routes/api.php`

**Оценка времени:** 4-6 часов

---

## ЭТАП 2: ВЫСОКИЙ ПРИОРИТЕТ (Полнота функциональности)

### 2.1. Рециркуляция

**Задача:** Реализовать управление рециркуляцией согласно `WATER_FLOW_ENGINE.md` раздел 11

**Шаги:**
1. Добавить параметры в targets рецепта (поддерживаются через JSONB):
   - `recirculation_enabled` (boolean)
   - `recirculation_interval_min` (int, минуты)
   - `recirculation_duration_sec` (int, секунды)

2. Доработать `irrigation_controller.py`:
   - Добавить функцию `check_and_control_recirculation(zone_id, targets)`
   - Логика: `if recirculation_enabled AND (now - last_recirculation >= interval) → run recirculation_pump`
   - Получение времени последней рециркуляции из событий RECIRCULATION_CYCLE
   - Создание события RECIRCULATION_CYCLE

3. Интегрировать в `automation-engine/main.py`:
   - Вызов после Irrigation Controller
   - Получение узла рециркуляции (тип `recirculation` или канал `recirculation_pump`)

**Файлы для изменения:**
- `backend/services/automation-engine/irrigation_controller.py`
- `backend/services/automation-engine/main.py`

**Оценка времени:** 3-4 часа

---

### 2.2. API endpoint `next_phase`

**Задача:** Добавить endpoint для автоматического перехода на следующую фазу рецепта

**Шаги:**
1. Добавить метод в `ZoneController.php`:
   ```php
   public function nextPhase(Zone $zone)
   {
       // Получить текущую фазу из zone_recipe_instances
       // Вычислить следующую фазу (current_phase_index + 1)
       // Вызвать zoneService->changePhase($zone, $nextPhaseIndex)
   }
   ```

2. Добавить route в `api.php`:
   ```php
   Route::post('zones/{zone}/next-phase', [ZoneController::class, 'nextPhase']);
   ```

3. Добавить валидацию:
   - Проверка, что есть следующая фаза
   - Проверка, что зона имеет активный рецепт

**Файлы для изменения:**
- `backend/laravel/app/Http/Controllers/ZoneController.php`
- `backend/laravel/routes/api.php`

**Оценка времени:** 1-2 часа

---

### 2.3. Расчет прогресса фазы для UI

**Задача:** Добавить расчет прогресса фазы в процентах для отображения в UI

**Шаги:**
1. Доработать `recipe_utils.py`:
   - Добавить функцию `calculate_phase_progress(zone_id) -> float` (0-100%)
   - Формула: `progress = (elapsed_hours / duration_hours) * 100`
   - Получение `elapsed_hours` из `zone_recipe_instances.phase_started_at`

2. Добавить поле `phase_progress` в ответ API:
   - В `ZoneController.php` при получении зоны добавить расчет прогресса
   - Или добавить в модель `ZoneRecipeInstance` accessor

3. Обновить frontend для отображения прогресса (если нужно)

**Файлы для изменения:**
- `backend/services/automation-engine/recipe_utils.py`
- `backend/laravel/app/Http/Controllers/ZoneController.php` (или модель)

**Оценка времени:** 2-3 часа

---

## ЭТАП 3: СРЕДНИЙ ПРИОРИТЕТ (Улучшения)

### 3.1. Scheduler Engine (полная архитектура)

**Задача:** Реализовать полную архитектуру согласно `GLOBAL_SCHEDULER_ENGINE.md`

**Шаги:**
1. Создать структуру:
   ```
   backend/services/scheduler/
   ├── core/
   │   ├── loop_engine.py
   │   ├── task_manager.py
   │   ├── cron_manager.py
   │   └── safety_guard.py
   ├── mqtt/
   │   ├── mqtt_router.py
   │   └── command_dispatcher.py
   └── main.py
   ```

2. Реализовать Safety Guard Layer:
   - Проверка NO_FLOW, LOW_WATER, OVERHEAT, NODE_OFFLINE, SENSOR_FAIL
   - Блокировка контроллеров при активации safety
   - Создание событий SAFETY_MODE_ACTIVATED, SAFETY_MODE_DEACTIVATED

3. Реализовать Housekeeping Engine:
   - Помечать узлы OFFLINE, если `last_seen_at > 90 сек`
   - Проверка зон без telemetry > 3 минут → статус WARNING
   - Очистка старых событий (опционально)

**Файлы для изменения:**
- `backend/services/scheduler/` (реструктуризация)

**Оценка времени:** 1-2 недели

---

### 3.2. Калибровка расхода

**Задача:** Реализовать режим калибровки согласно `WATER_FLOW_ENGINE.md` раздел 8

**Шаги:**
1. Добавить API endpoint: `POST /api/zones/{id}/calibrate-flow`
   - Параметры: `{"node_id": 123, "channel": "flow_sensor"}`

2. Реализовать алгоритм в `water_flow.py`:
   ```python
   async def calibrate_flow(zone_id: int, node_id: int, channel: str, mqtt: MqttClient, gh_uid: str) -> Dict[str, Any]
   ```
   - Запуск насоса на 10 сек
   - Измерение потока (получение данных из telemetry_samples)
   - Вычисление постоянной K (пульс → L/min)
   - Сохранение в node_channel.config через API

3. Добавить UI кнопку "Start Flow Calibration" (frontend)

**Файлы для изменения:**
- `backend/services/common/water_flow.py`
- `backend/laravel/app/Http/Controllers/ZoneController.php`
- `backend/laravel/routes/api.php`

**Оценка времени:** 4-6 часов

---

### 3.3. Zone Profile (hardware_profile, capabilities)

**Задача:** Добавить hardware_profile и capabilities согласно `ZONES_AND_PRESETS.md`

**Шаги:**
1. Создать миграцию:
   ```php
   Schema::table('zones', function (Blueprint $table) {
       $table->jsonb('hardware_profile')->nullable();
       $table->jsonb('capabilities')->nullable();
   });
   ```

2. Обновить модель `Zone`:
   - Добавить cast для JSONB полей
   - Добавить методы: `canPhControl()`, `canEcControl()`, и т.д.

3. Обновить контроллеры для проверки capabilities перед выполнением команд

**Файлы для изменения:**
- `backend/laravel/database/migrations/YYYY_MM_DD_add_zone_profile_fields.php` (новый)
- `backend/laravel/app/Models/Zone.php`
- `backend/services/automation-engine/*_controller.py` (добавить проверки)

**Оценка времени:** 3-4 часа

---

## ЭТАП 4: НИЗКИЙ ПРИОРИТЕТ (Опционально)

### 4.1. Реструктуризация контроллеров

**Задача:** Вынести контроллеры в папку `controllers/` для лучшей организации

**Шаги:**
1. Создать структуру:
   ```
   automation-engine/
   ├── controllers/
   │   ├── __init__.py
   │   ├── climate_controller.py
   │   ├── light_controller.py
   │   ├── irrigation_controller.py
   │   └── health_monitor.py
   ├── alerts_manager.py
   └── main.py
   ```

2. Обновить импорты в `main.py`

**Оценка времени:** 1 час

---

### 4.2. Presets (расширенные параметры)

**Задача:** Расширить структуру Preset согласно `ZONES_AND_PRESETS.md`

**Шаги:**
1. Проверить структуру таблицы `presets`
2. Добавить недостающие поля (если нужно):
   - `ph_optimal_range`, `ec_range`, `vpd_range`
   - `light_intensity_range`, `climate_ranges`
   - `irrigation_behavior`, `growth_profile`
   - `default_recipe_id`

**Оценка времени:** 2-3 часа

---

### 4.3. Расширенные targets

**Задача:** Добавить поддержку расширенных targets (VPD, Dynamic EC, Adaptive irrigation)

**Шаги:**
1. Обновить контроллеры для поддержки:
   - `temp_day`/`temp_night` в Climate Controller
   - `humidity_day`/`humidity_night` в Climate Controller
   - VPD targets (вычисление и контроль)
   - Dynamic EC (адаптация EC в зависимости от фазы)

**Оценка времени:** 1-2 недели

---

## ПРИОРИТИЗАЦИЯ ВЫПОЛНЕНИЯ

### Фаза 1 (Критично - 1-2 недели):
1. ✅ Интеграция защиты от сухого хода в scheduler (2-3 часа)
2. ✅ Режим Fill (4-6 часов)
3. ✅ Режим Drain (4-6 часов)

**Итого:** ~12-15 часов (2-3 рабочих дня)

### Фаза 2 (Важно - 1 неделя):
4. ✅ Рециркуляция (3-4 часа)
5. ✅ API endpoint `next_phase` (1-2 часа)
6. ✅ Расчет прогресса фазы (2-3 часа)

**Итого:** ~6-9 часов (1-2 рабочих дня)

### Фаза 3 (Улучшения - 2-3 недели):
7. Scheduler Engine (полная архитектура) (1-2 недели)
8. Калибровка расхода (4-6 часов)
9. Zone Profile (3-4 часа)

**Итого:** ~2-3 недели

### Фаза 4 (Опционально - по мере необходимости):
10. Реструктуризация контроллеров (1 час)
11. Presets (расширенные параметры) (2-3 часа)
12. Расширенные targets (1-2 недели)

---

## ЗАМЕТКИ

- Все изменения должны быть обратно совместимы
- Тестирование каждого этапа перед переходом к следующему
- Обновление документации при необходимости
- Ничего не удалять из существующего кода без крайней необходимости

---

## Конец плана
