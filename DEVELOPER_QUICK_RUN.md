# Developer Quick Run

Goal: a reproducible local bootstrap so an agent can start the system and spot regressions.

## Prerequisites

- Docker + Docker Compose (plugin or docker-compose)
- Python 3
- GNU Make

## Quick commands

```bash
make up
make migrate
make test
make lint
make smoke
```

Optional:

```bash
make down
```

## What each target does

- `make up`: start the dev stack using `backend/docker-compose.dev.yml`
- `make migrate`: run Laravel migrations in the dev stack
- `make test`: run PHP (phpunit) and Python (pytest) tests via containers
- `make lint`: run PHP lint via Pint in the Laravel container
- `make smoke`: run a short end-to-end smoke (telemetry -> DB, command -> MQTT)

## Smoke test details

The smoke test uses the E2E runner in `tests/e2e` and will:

- bring up the E2E docker-compose stack if it is not running
- run scenarios:
  - `core/E01_bootstrap.yaml`
  - `commands/E10_command_happy.yaml`
- write reports to `tests/e2e/reports`

Note: the E2E runner runs `php artisan migrate:fresh --seed` on the E2E database
if it is empty.

You can override the report output directory:

```bash
E2E_REPORT_DIR=/tmp/hydro_e2e_smoke make smoke
```
