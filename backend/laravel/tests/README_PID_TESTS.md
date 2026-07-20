# PID / correction authority tests

Канон: `zone.pid.*` + `zone.correction.controllers.*` (см. `doc_ai/06_DOMAIN_ZONES_RECIPES/PID_CONFIG_REFERENCE.md` §0).

Legacy `ZonePidConfig*` API/table и Python `adaptive_pid` / `pid_config_service` удалены.

## Laravel

```bash
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test --filter=ZonePid
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test --filter=ZoneCorrectionLiveEdit
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test --filter=AutomationConfigControllerZonePid
```

Живые поверхности: `ZonePidDefaults`, `ZonePidLogController` (pid-logs), PidConfigForm → automation-configs `zone.pid.*`.

## Python (AE3)

```bash
COMPOSE_PROFILES=tests docker compose -f backend/docker-compose.dev.yml run --rm pid-tests
# или:
make test-ae PYTEST_ARGS="-q test_ae3lite_pid_output_event.py test_ae3lite_pid_state_repository.py test_ae3lite_correction_planner.py"
```

Скрипт-обёртка: `./run_pid_tests.sh python`
