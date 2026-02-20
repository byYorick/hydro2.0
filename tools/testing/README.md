# E2E Testing Tools

Инструменты для запуска end-to-end тестов системы Hydro 2.0.

## Быстрый старт

### One-command запуск

```bash
./tools/testing/run_e2e.sh
```

Этот скрипт:
1. Поднимает все сервисы через Docker Compose
2. Дожидается readiness всех сервисов
3. Запускает обязательные E2E сценарии
4. Генерирует отчёты
5. Выводит summary с результатами

### AE2 S12 staging gate (one-command)

Для S12 acceptance gate (cutover SLO baseline + release decision):

```bash
AE2_SLO_PROBE_BASE_URL=http://<staging-ae-host>:<port> \
AE2_SLO_PROBE_AUTHORIZATION='Bearer <token>' \
./tools/testing/run_ae2_s12_staging_gate.sh
```
Этот wrapper автоматически выполняет bundle-check (`check_ae2_s12_release_bundle.sh`).
Также wrapper автоматически формирует summary markdown (по умолчанию в `doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_SUMMARY.md`).
Также wrapper автоматически формирует metadata json (по умолчанию в `doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_METADATA.json`).

Local dry-run без стенда:

```bash
AE2_SLO_PROBE_MODE=local \
AE2_S12_BASELINE_CSV=artifacts/ae2_s12_local_baseline.csv \
AE2_S12_DECISION_TXT=artifacts/ae2_s12_local_decision.txt \
./tools/testing/run_ae2_s12_staging_gate.sh
```

### AE2 invariants (machine guard rails)

```bash
./tools/testing/check_ae2_invariants.sh
```

Проверки:
1. publish path на history-logger только через `infrastructure/command_bus.py`;
2. отсутствие прямого MQTT publish в runtime-коде `automation-engine`;
3. централизация executor feature flags в `application/executor_constants.py`;
4. отсутствие SQL DDL (`CREATE/ALTER/DROP TABLE`) в Python-сервисах.

Отключить auto-check wrapper (debug-only):

```bash
AE2_S12_RUN_BUNDLE_CHECK=false ./tools/testing/run_ae2_s12_staging_gate.sh
```

Отключить auto-summary wrapper (debug-only):

```bash
AE2_S12_WRITE_SUMMARY=false ./tools/testing/run_ae2_s12_staging_gate.sh
```

Отключить auto-metadata wrapper (debug-only):

```bash
AE2_S12_WRITE_METADATA=false ./tools/testing/run_ae2_s12_staging_gate.sh
```

Ручная сборка summary:

```bash
python3 tools/testing/build_ae2_s12_gate_summary.py \
  --baseline-csv doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_BASELINE.csv \
  --decision-txt doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_RELEASE_DECISION.txt \
  --output-md doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_SUMMARY.md \
  --mode remote
```

Ручная сборка metadata:

```bash
python3 tools/testing/build_ae2_s12_gate_metadata.py \
  --mode remote \
  --baseline-csv doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_BASELINE.csv \
  --decision-txt doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_RELEASE_DECISION.txt \
  --summary-md doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_SUMMARY.md \
  --output-json doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_METADATA.json \
  --base-url http://<staging-ae-host>:<port> \
  --requests 240 \
  --concurrency 40 \
  --bootstrap-wait-sec 60 \
  --run-bundle-check true \
  --expect-decision ALLOW_FULL_ROLLOUT
```

Проверка целостности release bundle (baseline + decision):

```bash
./tools/testing/check_ae2_s12_release_bundle.sh
```

По умолчанию checker strict и требует `decision=ALLOW_FULL_ROLLOUT`.
Диагностический режим (без strict expected-decision):

```bash
AE2_S12_EXPECT_DECISION=ANY ./tools/testing/check_ae2_s12_release_bundle.sh
```
`AE2_S12_EXPECT_DECISION` обрабатывается case-insensitive и принимает оба формата:
- `ALLOW_FULL_ROLLOUT`
- `decision=allow_full_rollout`

Финальная строгая проверка для стендового прогона:

```bash
AE2_S12_REQUIRE_REMOTE_METADATA=true ./tools/testing/check_ae2_s12_release_bundle.sh
```

Полный one-command flow (staging gate + auto finalize документов):

```bash
AE2_SLO_PROBE_BASE_URL=http://<staging-ae-host>:<port> \
AE2_SLO_PROBE_AUTHORIZATION='Bearer <token>' \
AE2_S12_AUTO_FINALIZE_DOCS=true \
./tools/testing/run_ae2_s12_staging_gate.sh
```
Этот режим рассчитан на `remote` прогон и требует включенного bundle-check (`AE2_S12_RUN_BUNDLE_CHECK=true`, default).
Также для auto-finalize должен быть включен metadata artifact (`AE2_S12_WRITE_METADATA=true`, default).
Для auto-finalize нельзя использовать `AE2_S12_EXPECT_DECISION=ANY` (требуется strict expected decision, default `ALLOW_FULL_ROLLOUT`).
Для auto-finalize требуется `AE2_S12_EXPECT_DECISION=ALLOW_FULL_ROLLOUT`.
При `AE2_S12_AUTO_FINALIZE_DOCS=true` wrapper автоматически включает strict remote metadata check на шаге bundle-check (`AE2_S12_REQUIRE_REMOTE_METADATA=true`).

Автофинализация S12-документов (использовать только после strict gate PASS):

```bash
python3 tools/testing/finalize_ae2_s12_docs.py
python3 tools/testing/finalize_ae2_s12_docs.py --apply
```

Небезопасный override (только аварийный сценарий, не использовать для обычного stage-gate):

```bash
AE2_S12_ALLOW_UNSAFE_FINALIZE=true \
python3 tools/testing/finalize_ae2_s12_docs.py --apply --skip-gate-check
```

### Результат

При успешном выполнении:
```
E2E Test Summary
==========================================
Total scenarios: 5
Passed: 5
Failed: 0

All scenarios passed! ✓

Reports location: tests/e2e/reports/
  - junit.xml
  - timeline.json
```

При ошибках:
```
E2E Test Summary
==========================================
Total scenarios: 5
Passed: 3
Failed: 2

Failed scenarios:
  - commands/E10_command_happy
  - alerts/E20_error_to_alert_realtime

Service logs:
  docker compose -f tests/e2e/docker-compose.e2e.yml logs laravel
  docker compose -f tests/e2e/docker-compose.e2e.yml logs history-logger
  docker compose -f tests/e2e/docker-compose.e2e.yml logs node-sim
```

## Настройка

### Переменные окружения

Скрипт использует файл `tests/e2e/.env.e2e` для конфигурации.

Если файл отсутствует, создайте его из примера:
```bash
cp tests/e2e/.env.e2e.example tests/e2e/.env.e2e
# Отредактируйте значения при необходимости
```

### Основные параметры

- `LARAVEL_PORT` - порт Laravel API (по умолчанию 8081)
- `POSTGRES_PORT` - порт PostgreSQL (по умолчанию 5433)
- `MQTT_PORT` - порт MQTT брокера (по умолчанию 1884)
- `LARAVEL_API_TOKEN` - опционально (legacy), по умолчанию используется AuthClient

## Ручной запуск

Если нужно запустить тесты вручную:

```bash
cd tests/e2e

# Поднять сервисы
docker compose -f docker-compose.e2e.yml up -d

# Дождаться готовности
sleep 30

# Запустить сценарий
python3 -m runner.e2e_runner scenarios/core/E01_bootstrap.yaml

# Остановить сервисы
docker compose -f docker-compose.e2e.yml down
```

## Отчёты

После выполнения тестов отчёты сохраняются в `tests/e2e/reports/`:

- `junit.xml` - JUnit XML формат для CI/CD
- `timeline.json` - JSON timeline с детальной информацией
- Последние 50 WS/MQTT сообщений включены в timeline

## Troubleshooting

### Сервисы не поднимаются

```bash
# Проверить логи
docker compose -f tests/e2e/docker-compose.e2e.yml logs

# Проверить статус
docker compose -f tests/e2e/docker-compose.e2e.yml ps

# Пересоздать контейнеры
docker compose -f tests/e2e/docker-compose.e2e.yml down -v
docker compose -f tests/e2e/docker-compose.e2e.yml up -d
```

### node-sim не подключается к MQTT

```bash
# Проверить логи node-sim
docker compose -f tests/e2e/docker-compose.e2e.yml logs node-sim

# Проверить MQTT брокер
docker compose -f tests/e2e/docker-compose.e2e.yml logs mosquitto

# Проверить конфигурацию
cat tests/e2e/node-sim-config.yaml
```

### Тесты падают

1. Проверить логи сервисов
2. Проверить отчёты в `tests/e2e/reports/`
3. Проверить переменные окружения
4. Убедиться, что все сервисы healthy

## Дополнительная информация

- Полная документация: `../../docs/testing/E2E_GUIDE.md`
- Troubleshooting: `../../docs/testing/TROUBLESHOOTING.md`
- Node Simulator: `../../docs/testing/NODE_SIM.md`
