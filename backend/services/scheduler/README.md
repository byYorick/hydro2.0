# scheduler (legacy placeholder)

**Статус:** не используется в runtime. Отдельного Python/контейнера scheduler в compose **нет**.

## Канон (код = SoT)

Владелец расписаний — **Laravel**:

1. `automation:dispatch-schedules` (см. `routes/console.php`)
2. запись intent в `zone_automation_intents`
3. wake-up AE3:
   - `POST /zones/{id}/start-irrigation`
   - `POST /zones/{id}/start-lighting-tick`
   - `POST /zones/{id}/start-solution-topup`
   - `POST /zones/{id}/start-solution-change`
   - `POST /zones/{id}/start-cycle` (diagnostics / cycle_start)
   - `POST /greenhouses/{id}/start-climate-tick`
4. команды к узлам — **только** через `history-logger` → MQTT

Документация: `doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md`, `doc_ai/SYNC_PLAN.md`.

Эта папка сохранена как historical placeholder; не добавлять сюда production dispatch.
