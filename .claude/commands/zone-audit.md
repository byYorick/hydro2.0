---
description: Полный аудит зоны — конфиг, effective targets, PID state, recent telemetry, calibration
argument-hint: <zone_id>
allowed-tools: Bash(psql:*), Bash(curl:*), Bash(jq:*)
---

Пользователь хочет аудит зоны **$ARGUMENTS** (read-only, без изменений). Если аргумент пустой — попроси указать `zone_id`.

## Секции аудита (выполни параллельно где можно)

### 1. Базовая конфигурация зоны
```
psql -h localhost -U hydro -d hydro_dev -c "SELECT id, uid, title, automation_runtime, logic_profile, ec_dosing_mode, active_recipe_id, active_cycle_id FROM zones WHERE id=$ARGUMENTS"
```

### 2. Correction config (PID params, limits)
```
psql -h localhost -U hydro -d hydro_dev -c "SELECT correction_config FROM zones WHERE id=$ARGUMENTS" | cat
```
Распарси JSON через `jq` и покажи структурно: `controllers.ph`, `controllers.ec`, `pump_calibration` для каждого насоса.

### 3. Effective targets (если есть активная фаза)
```
curl -s http://localhost:9405/zones/$ARGUMENTS/effective-targets | jq .
```
Проверь что pH/EC target|min|max **не null** — иначе это `PlannerConfigurationError` (fail-closed).

### 4. PID state (актуальное состояние контроллеров)
```
psql -h localhost -U hydro -d hydro_dev -c "SELECT pid_type, integral, last_measurement_at, last_dose_at, no_effect_count FROM pid_state WHERE zone_id=$ARGUMENTS"
```
Флаги: `no_effect_count >= 3` = fail-closed window; `last_measurement_at` старше 10 мин = stale.

### 5. Последняя телеметрия
```
psql -h localhost -U hydro -d hydro_dev -c "SELECT metric_type, value, unit, ts, stable FROM telemetry_last WHERE zone_id=$ARGUMENTS ORDER BY metric_type"
```
Проверь sanity bounds: pH ∈ [0,14], EC ∈ [0,20] mS/cm. Выход = `sensor_out_of_bounds`.

### 6. Узлы зоны и их статус
```
psql -h localhost -U hydro -d hydro_dev -c "SELECT n.uid, n.type, n.status, n.last_seen_at FROM nodes n JOIN node_zones nz ON nz.node_id=n.id WHERE nz.zone_id=$ARGUMENTS"
```

### 7. Последние команды (24ч) — успехи/провалы
```
psql -h localhost -U hydro -d hydro_dev -c "SELECT status, COUNT(*) FROM commands WHERE zone_id=$ARGUMENTS AND created_at > now() - interval '24 hours' GROUP BY status ORDER BY 2 DESC"
```

### 8. Active alerts
```
psql -h localhost -U hydro -d hydro_dev -c "SELECT type, severity, COUNT(*) FROM alerts WHERE zone_id=$ARGUMENTS AND acknowledged_at IS NULL GROUP BY type, severity"
```

## Формат ответа

Структурируй по секциям с заголовками `##`. В **конце** сделай **Summary** в виде чек-листа:
- ✅/❌ Конфиг валиден (runtime=ae3, correction_config не null)
- ✅/❌ Effective targets присутствуют (pH + EC)
- ✅/❌ PID state свежий (last_measurement_at < 10 мин)
- ✅/❌ Телеметрия в sanity bounds
- ✅/❌ Узлы online
- ⚠️ Обнаруженные проблемы (если есть)

Не предлагай действия без запроса пользователя — это read-only аудит.
