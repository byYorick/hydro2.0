# План: Исправление багов PID-системы после реализации Agents 1–4

**Дата:** 2026-03-04
**Ветка:** `ae3`
**Приоритет:** Критические → Важные → Минорные

---

## Баг 1 🔴 AE: отсутствует GET /zones/{id}/relay-autotune/status

### Проблема
`api_runtime_zone_routes.py` содержит только `POST /zones/{zone_id}/start-relay-autotune`.
`GET /zones/{zone_id}/relay-autotune/status` не существует.
Laravel `ZoneRelayAutotuneController::status()` вызывает этот endpoint каждые 10 сек → 404 → фронт не видит прогресс.

### Файл
`backend/services/automation-engine/ae2lite/api_runtime_zone_routes.py`

### Изменение
Добавить **перед** `return (...)` (строка ~328) новый route:

```python
@app.get("/zones/{zone_id}/relay-autotune/status")
async def zone_relay_autotune_status(zone_id: int):
    zone_service = get_zone_service_fn() if callable(get_zone_service_fn) else None
    result = {}
    for pid_type, ctrl_name in (("ph", "ph_controller"), ("ec", "ec_controller")):
        controller = getattr(zone_service, ctrl_name, None) if zone_service else None
        autotune_by_zone = getattr(controller, "_autotune_by_zone", {}) if controller else {}
        autotuner = autotune_by_zone.get(zone_id)

        if autotuner is None:
            result[pid_type] = {"status": "idle"}
        elif autotuner.is_complete:
            r = autotuner.result
            result[pid_type] = {
                "status": "complete",
                "result": {
                    "source": "relay_autotune",
                    "ku": float(getattr(r, "ku", 0.0)),
                    "tu_sec": float(getattr(r, "tu_sec", 0.0)),
                    "kp": float(getattr(r, "kp", 0.0)),
                    "ki": float(getattr(r, "ki", 0.0)),
                    "oscillation_amplitude": float(getattr(r, "oscillation_amplitude", 0.0)),
                    "cycles_detected": int(getattr(r, "cycles_detected", 0)),
                    "tuned_at": getattr(r, "tuned_at", None),
                } if r else None,
            }
        elif autotuner.is_timed_out:
            result[pid_type] = {"status": "timeout"}
        else:
            elapsed = time.monotonic() - autotuner.start_time_sec
            result[pid_type] = {
                "status": "running",
                "progress": {
                    "cycles_detected": autotuner._zero_crossings // 2,
                    "min_cycles": autotuner.config.min_cycles,
                    "elapsed_sec": round(elapsed, 1),
                    "max_duration_sec": autotuner.config.max_duration_sec,
                },
            }

    return {"status": "ok", "zone_id": zone_id, "data": result}
```

**Импорт:** `time` уже импортирован в файле.

### Проверка
```bash
curl http://localhost:9405/zones/1/relay-autotune/status
# {"status": "ok", "zone_id": 1, "data": {"ph": {"status": "idle"}, "ec": {"status": "idle"}}}
```

---

## Баг 2 🔴 Python: ключ `autotune` → `autotune_meta` (несовпадение с TypeScript)

### Проблема
`pid_config_service.py` сохраняет результат автотюна в `config_json["autotune"]`.
TypeScript тип `PidConfig` ожидает поле `autotune_meta`.
Фронт не отображает результаты автотюна в `PidConfigForm.vue`.

### Файл
`backend/services/automation-engine/services/pid_config_service.py`

### Изменения

**1. В `save_autotune_result()` (строка ~226) переименовать ключ:**
```python
# было:
config_json["autotune"] = { ... }
# стало:
config_json["autotune_meta"] = { ... }
```

**2. В `save_autotune_result()` событие `PID_CONFIG_UPDATED` обновить:**
```python
await create_zone_event(
    zone_id,
    "PID_CONFIG_UPDATED",
    {
        "type": pid_type,
        "source": "relay_autotune",
        "new_config": {
            "zone_coeffs": {
                "close": {"kp": close["kp"], "ki": close["ki"], "kd": close["kd"]},
                "far": {"kp": far["kp"], "ki": far["ki"], "kd": far["kd"]},
            }
        },
        "autotune_meta": config_json.get("autotune_meta"),  # переименовать
    },
)
```

**3. В `_pid_config_to_json()` (строка ~398) добавить `autotune_meta` в output:**
```python
result = {
    "target": float(config.setpoint),
    ...
    "min_interval_ms": int(config.min_interval_ms),
}
# Сохраняем autotune_meta если он есть в конфиге
# (не в AdaptivePidConfig, но нужен при round-trip через _json_to_pid_config)
return result
```

**4. В `_json_to_pid_config()` добавить обратную совместимость:**
```python
# Поддержка старого ключа 'autotune' (до переименования)
# autotune_meta хранится в JSONB, но не в AdaptivePidConfig
# → передаётся через config['autotune_meta'] отдельно
```
Примечание: `autotune_meta` не входит в `AdaptivePidConfig` (только runtime данные).
Laravel читает JSONB напрямую и возвращает фронту `config.autotune_meta` — всё корректно после переименования.

---

## Баг 3 🔴 AE: несовпадение имени события + отсутствует RELAY_AUTOTUNE_COMPLETED

### Проблема A: Имя события при запуске
AE создаёт: `PID_RELAY_AUTOTUNE_STARTED`
i18n.js ожидает: `RELAY_AUTOTUNE_STARTED`
→ событие не отображается в zone events на фронте.

### Проблема B: Отсутствует событие завершения
При успешном автотюне AE создаёт только `PID_CONFIG_UPDATED`.
i18n.js ожидает: `RELAY_AUTOTUNE_COMPLETED`
→ пользователь не видит результат в ленте событий.

### Файлы
- `backend/services/automation-engine/ae2lite/api_runtime_zone_routes.py`
- `backend/services/automation-engine/services/pid_config_service.py`
- `backend/services/automation-engine/correction_controller_check_core.py`

### Изменение A: в `api_runtime_zone_routes.py` (строка ~315)
```python
# было:
"PID_RELAY_AUTOTUNE_STARTED",
# стало:
"RELAY_AUTOTUNE_STARTED",
```

### Изменение B: в `pid_config_service.save_autotune_result()` — добавить второе событие
После `await create_zone_event(zone_id, "PID_CONFIG_UPDATED", {...})` добавить:
```python
await create_zone_event(
    zone_id,
    "RELAY_AUTOTUNE_COMPLETED",
    {
        "type": pid_type,
        "source": "relay_autotune",
        "kp": kp,
        "ki": ki,
        "kd": kd,
        "ku": float(result.get("ku") or 0.0),
        "tu_sec": float(result.get("tu_sec") or 0.0),
        "oscillation_amplitude": float(result.get("oscillation_amplitude") or 0.0),
        "cycles_detected": int(result.get("cycles_detected") or 0),
        "duration_sec": float(result.get("duration_sec") or 0.0),
        "tuned_at": result.get("tuned_at"),
    },
)
```

### Проверка
- Запустить автотюн → в zone events появляется `RELAY_AUTOTUNE_STARTED` (ACTION, синий)
- После завершения → `RELAY_AUTOTUNE_COMPLETED` и `PID_CONFIG_UPDATED`

---

## Баг 4 🟡 Миграция не применена

### Проблема
`2026_03_05_000001_update_pid_state_add_wallclock.php` создана, но не применена.
Без неё `pid_state_manager.py` падает при сохранении `last_dose_at` (колонки нет).
→ Fix монотонного таймера не работает, PID-состояние не сохраняется.

### Действие
```bash
make migrate
# или:
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan migrate
```

### Проверка
```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'pid_state' AND column_name IN ('last_dose_at', 'prev_derivative');
-- Должны быть обе колонки
```

---

## Баг 5 🟡 `pump_calibrations` пуста — EC по-прежнему не дозирует

### Проблема
Таблица `pump_calibrations` не заполнена. EC коррекция работает но дозирует `0 мл`.
`PumpCalibrationsPanel.vue` создан, но пользователь должен вручную ввести данные.
Для dev/staging нужны дефолтные данные.

### Файл
`backend/laravel/database/seeders/LiteAutomationSeeder.php`

### Изменение: добавить вызов нового метода в `run()`
После `$this->createInfrastructure($zones, $zoneNodes)`:
```php
$this->seedPumpCalibrations($zoneNodes);
```

Новый метод `seedPumpCalibrations()`:
```php
private function seedPumpCalibrations(array $zoneNodes): void
{
    // Дефолтные скорости насосов (мл/сек)
    $defaults = [
        'ph_acid_pump'      => 0.5,
        'ph_base_pump'      => 0.5,
        'ec_npk_pump'       => 1.0,
        'ec_calcium_pump'   => 1.0,
        'ec_magnesium_pump' => 1.0,
        'ec_micro_pump'     => 0.8,
    ];

    foreach ($zoneNodes as $zone => $nodes) {
        foreach ($nodes as $node) {
            foreach ($node->channels ?? [] as $channel) {
                $role = $channel->bindings()->first()?->role;
                if (!$role || !isset($defaults[$role])) continue;

                \DB::table('pump_calibrations')->upsert([
                    'node_channel_id' => $channel->id,
                    'ml_per_sec'      => $defaults[$role],
                    'component'       => str_replace(['ph_', 'ec_', '_pump'], '', $role),
                    'source'          => 'default',
                    'is_active'       => true,
                    'valid_from'      => now(),
                    'valid_to'        => null,
                    'created_at'      => now(),
                    'updated_at'      => now(),
                ], ['node_channel_id'], ['ml_per_sec', 'source', 'updated_at']);
            }
        }
    }
    $this->command->info('Pump calibrations seeded with defaults');
}
```

Адаптировать под реальную структуру `$zoneNodes` в seeder-е (проверить тип).

---

## Баг 6 🟡 Старые записи `zone_pid_configs` с `Ki=0`

### Проблема
Если в БД есть записи с `zone_coeffs.close.ki = 0` (созданные до исправления),
они переопределяют новые дефолты из `settings.py`.
PID работает как P-only несмотря на исправление.

### Решение A (рекомендуется): Data migration
```sql
-- Удалить все старые конфиги (AE загрузит новые из settings.py)
-- ВНИМАНИЕ: пользовательские конфиги также будут удалены
DELETE FROM zone_pid_configs
WHERE (config->'zone_coeffs'->'close'->>'ki')::float = 0
  AND (config->'zone_coeffs'->'far'->>'ki')::float = 0;
```

### Решение B (безопаснее): в `pid_config_service._json_to_pid_config()`
После получения Ki из JSONB — если Ki <= 0, применить дефолт из settings:
```python
ki_close = float(coeffs['close'].get('ki', 0.0))
if ki_close <= 0:
    ki_close = settings.PH_PID_KI_CLOSE if correction_type == 'ph' else settings.EC_PID_KI_CLOSE
```
Аналогично для `ki_far`.

**Рекомендуется решение B** — оно не уничтожает пользовательские Kp настройки.

---

## Баг 7 🟢 Мёртвый код: `getEnableAutotuneAttribute()` в `ZonePidConfig.php`

### Проблема
`ZonePidConfig.php` строка ~119 содержит accessor для несуществующего поля.

### Файл
`backend/laravel/app/Models/ZonePidConfig.php`

### Изменение
Удалить метод:
```php
public function getEnableAutotuneAttribute(): ?bool
{
    return $this->config['enable_autotune'] ?? null;
}
```

---

## Порядок выполнения

```
1. Баг 4 (make migrate)        — без этого pid_state_manager падает
2. Баг 1 (AE status endpoint)  — без этого статус автотюна недоступен
3. Баг 2 (autotune_meta)       — без этого результаты не отображаются
4. Баг 3A (имя события)        — без этого событие запуска не отображается
5. Баг 3B (RELAY_AUTOTUNE_COMPLETED) — без этого нет события завершения
6. Баг 5 (pump calibrations)   — без этого EC не дозирует в dev
7. Баг 6 (Ki=0 configs)        — fix в pid_config_service.py (безопасный)
8. Баг 7 (мёртвый код)         — последним
```

---

## Критерии готовности

- [ ] `GET /zones/{id}/relay-autotune/status` возвращает `{"status": "idle"}` для неактивной зоны
- [ ] Запуск автотюна → в zone events появляется `RELAY_AUTOTUNE_STARTED`
- [ ] Завершение автотюна → появляется `RELAY_AUTOTUNE_COMPLETED` с Kp/Ki
- [ ] После завершения автотюна → `PidConfigForm.vue` показывает `autotune_meta` блок
- [ ] `pid_state` таблица содержит колонки `last_dose_at` и `prev_derivative`
- [ ] EC коррекция логирует дозирование (нет "invalid pump calibration" WARNING)
- [ ] `make test` — все тесты зелёные
