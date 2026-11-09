# Развёртывание текущего Docker-стека Hydro 2.0

**Статус:** guide. **Сверено:** 2026-11-07 по Compose, Dockerfile и Makefile.

## Источники конфигурации

- Dev: [docker-compose.dev.yml](../../backend/docker-compose.dev.yml),
  [Laravel Dockerfile](../../backend/laravel/Dockerfile), [DB Dockerfile](../../backend/services/db/Dockerfile).
- Production: [docker-compose.prod.yml](../../backend/docker-compose.prod.yml),
  [Laravel Dockerfile.prod](../../backend/laravel/Dockerfile.prod).
- Команды и env-файлы задаёт [Makefile](../../Makefile). Отдельного корневого
  `docker-compose.yml` нет; команды ниже выполняются из корня репозитория.

Не создавайте Compose/Dockerfile заново по примеру из документации: рабочие файлы
уже содержат mounts, healthchecks, auth, profiles и параметры запуска.

## Состав и версии

Laravel 12 / PHP 8.2, Inertia 2 + Vue 3, Sanctum и Reverb заданы composer/package
manifest. Dev PHP-образ включает Node 20. Python-сервисы используют собственные
requirements и Dockerfile; общий код расположен в `backend/services/common/`.

| Сервис | Назначение | Обычный dev `make up` |
|---|---|---|
| `mqtt` | Mosquitto, auth/ACL, транспорт нод | да |
| `db` | PostgreSQL 16 + TimescaleDB + pg_cron | да |
| `redis` | Кеш/очереди Laravel, сервисные очереди | да |
| `laravel` | API/UI, конфигурация, scheduler-dispatch, Reverb | да |
| `mqtt-bridge` | Metrics и live-status probe; не command/config API | да |
| `history-logger` | MQTT ingest, БД и единственная публикация device-команд | да |
| `automation-engine` | AE3 workflow и greenhouse climate | да |
| `telemetry-aggregator` | Непрерывная агрегация и очистка telemetry | да |
| Monitoring + exporters | Prometheus, Grafana, Alertmanager | profile `obs` |
| `digital-twin`, `node-sim-manager` | Симуляция | profile `sim` |
| `feature-builder` | Frozen skeleton | profile `ml` |
| `node-emulator` | Нагрузочная эмуляция | profile `load-test` |

Production Compose имеет свой состав: в нём нет dev `feature-builder`,
`node-sim-manager`, `node-emulator` и тестовых контейнеров. Не переносите dev-профили
в production без проверки выбранного Compose-файла.

Dev DB-образ закреплён на TimescaleDB **2.26.0-pg16**, production —
**2.28.2-pg16**. При переносе volume/backup проверьте версию расширения и направление
обновления; одинаковая major PostgreSQL не означает взаимозаменяемость образов.

## Development

```bash
make up-build   # при первой сборке или изменении Dockerfile/dependencies
make migrate    # миграции и DevBootstrapSeeder
make logs-core
```

Для обычного запуска с существующими образами: `make up` (pull missing, без
принудительной пересборки). Без pull/build: `make up-offline`, если образы уже есть.
`ensure-dev-secrets` подготавливает `backend/.env`; не публикуйте его значения.
Запуск контейнера не заменяет явную проверку миграций через `make migrate`.

```bash
make up-obs
# Опциональные контуры запускаются отдельно по задаче:
# make up-sim
# make up-ml
```

`make refresh`, `make reset-db`, `down -v` удаляют данные/состояние и не являются
обычными шагами bootstrap или диагностики.

## Development: доступ с хоста

| Сервис | Адрес/порт |
|---|---|
| Laravel | `http://localhost:8080` |
| Vite | `5173` |
| Reverb | `6001` |
| mqtt-bridge | `9000` |
| history-logger | `9300` (REST и `/metrics`) |
| automation-engine | `9405` (REST и `/metrics/`) |
| telemetry-aggregator | `9404` |
| PostgreSQL / Redis / MQTT | `5432` / `6379` / `1883`, по умолчанию loopback |
| Prometheus / Grafana / Alertmanager | `9090` / `3000` / `9093`, profile `obs` |

Внутри Compose используются DNS-имена сервисов и их внутренние порты.
`localhost` внутри контейнера не обозначает соседний контейнер или Docker host.
Для ESP32 нужен доступный сетевой адрес хоста и настроенный bind/firewall;
loopback MQTT 1883 недоступен устройству из LAN по умолчанию.

Проверка уже запущенного dev-стека:

```bash
curl --fail --silent --show-error http://localhost:9300/health
curl --fail --silent --show-error http://localhost:9405/health/live
curl --fail --silent --show-error http://localhost:9405/health/ready
```

HTTP 200 health-check не является проверкой исполнения команд на железе.
HL подписывается на конкретные topic patterns, а не на широкий `hydro/#`;
контракт подписок — [MQTT_SPEC_FULL.md](../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md).

## Production

Production использует `backend/.env.prod` и явный Compose-файл через Makefile:

```bash
make prod-setup
make prod-check
make prod-up
make prod-migrate
make prod-ps
```

`prod-setup` подготавливает конфигурацию развёртывания; проверьте её до запуска.
`prod-seed` — отдельное действие с `StartUsersSeeder`, не обязательный шаг
восстановления существующей БД. Monitoring подключается через `COMPOSE_PROFILES=obs`.

В production опубликованы Laravel `8080`, Reverb `6001`, MQTT `1883/8883` и,
при profile `obs`, Grafana `3000`. PostgreSQL, Redis, HL, AE3, mqtt-bridge,
Prometheus и Alertmanager не имеют host port mapping. Доступ к ним проверяется
в выбранной контейнерной сети/через явно настроенный канал, не по dev localhost URL.
MQTT listener/bind, TLS-файлы и `MQTT_PLAINTEXT_ENABLED` проверяются отдельно;
наличие 8883 mapping не доказывает активный TLS listener.

## Резервное копирование

Laravel использует mounted `/scripts/backup` и read-only `/backup-sources`. `backup:full` по умолчанию сохраняет DB dump и конфигурации приложения/MQTT; Docker volumes отключены и отмечены в manifest. Dockerfiles устанавливают PostgreSQL client 16 и archive tools. Перед вводом стенда проверьте manifest и восстановление — [BACKUP_AND_RECOVERY.md](../08_SECURITY_AND_OPS/BACKUP_AND_RECOVERY.md).

## Проверки перед изменением конфигурации

Проверьте выбранные profiles, ports, mounts, healthchecks и env-binding.
`docker compose ... config --quiet` валидирует конфигурацию без печати раскрытых
секретов. Полный `config`/`env` не включайте в отчёты.
Защищённые command/config contracts — [PYTHON_SERVICES_ARCH.md](PYTHON_SERVICES_ARCH.md),
[HISTORY_LOGGER_API.md](HISTORY_LOGGER_API.md), [ARCHITECTURE_FLOWS.md](../ARCHITECTURE_FLOWS.md).
Восстановление существующих данных — по [BACKUP_AND_RECOVERY.md](../08_SECURITY_AND_OPS/BACKUP_AND_RECOVERY.md).

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
