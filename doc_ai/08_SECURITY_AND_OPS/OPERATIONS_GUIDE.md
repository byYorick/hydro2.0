# OPERATIONS_GUIDE.md
# Эксплуатация Hydro 2.0

**Сверено с кодом:** 2026-11-07. Команды dev ниже выполняются из корня репозитория. Production использует `backend/docker-compose.prod.yml` и `backend/.env.prod`; доступность host-портов отличается от dev.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Ежедневные проверки

```bash
# Dev: состав и состояние контейнеров
docker compose -f backend/docker-compose.dev.yml ps
make logs SERVICE=laravel TAIL=100

# Production: использовать отдельный Compose/env
make prod-ps
make prod-logs SERVICE=laravel TAIL=100
```

Логи с `-f` следуют за выводом; завершение просмотра — Ctrl+C. Core-стек содержит MQTT, PostgreSQL, Redis, Laravel, history-logger, mqtt-bridge, AE3 и telemetry-aggregator. Monitoring — профиль `obs` (`make up-obs` в dev), simulation/ML — отдельные profiles.

Dev HTTP-проверки:

```bash
curl -fsS http://localhost:8080/api/system/health
curl -fsS http://localhost:9300/health
curl -fsS http://localhost:9405/health/live
curl -fsS http://localhost:9405/health/ready
```

В production HL/AE/DB/Redis не публикуют эти host-порты. Проверять их нужно внутри Compose-сети или через отдельно настроенный monitoring. `mqtt-bridge` предоставляет `/metrics` и live-status probe; команды публикует только history-logger.

`/api/system/scheduler/metrics` использует `verify.scheduler.metrics`: при настроенном `AUTOMATION_LARAVEL_SCHEDULER_METRICS_TOKEN` нужен соответствующий Bearer token. UI алертов — `/alerts`; ack переводит ACTIVE в RESOLVED. Доступ к данным определяется ролью и scope пользователя.

## Расписания и хранение

Для просмотра Laravel Schedule в dev:

```bash
docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan schedule:list
```

`Schedule::command` описывает план, а не факт успешного запуска. Проверяйте scheduler process, логи, метрики pending intents/active tasks и результаты jobs. `schedule:test` выполняет выбранное задание и не является просмотром последнего запуска.

Фактические jobs из `routes/console.php`:

| Job | Расписание / роль |
|---|---|
| `telemetry:cleanup-raw` | ежедневно 02:00, default 30d |
| `logs:cleanup --days=30` | воскресенье 02:00 |
| `ae3:cleanup-old-tasks --days=90` | ежедневно 03:30 |
| `backup:full` | ежедневно 03:00; application scope по умолчанию, см. ниже |
| `rotate_backups.sh` | ежедневно 03:30 из настроенного backup script directory |

Непрерывный writer агрегатов — Python telemetry-aggregator. `telemetry:aggregate` и `commands:archive` / `zone-events:archive` не включены в Schedule. Сроки и ограничения — [DATA_RETENTION_POLICY.md](../05_DATA_AND_STORAGE/DATA_RETENTION_POLICY.md).

## Проверка бэкапов

Проверяйте manifest, exit code, состав архивов и пробное восстановление в отдельную БД. Дата файла, успешный zip или запись в Schedule не доказывают восстановимость всей системы.

Стандартный dev/prod Compose предоставляет `/scripts/backup` и read-only `/backup-sources`. `backup:full` использует активный Laravel config для БД и APP_KEY; создаёт application backup без Docker daemon. Manifest явно показывает scope и пропущенные компоненты; ошибка запрошенного компонента завершает команду ошибкой. Для включения volume-компонента требуется отдельное подготовленное окружение и `BACKUP_INCLUDE_DOCKER_VOLUMES=true`.

`mqtt_backup.sh` сохраняет доступные dev/prod конфиги, обязательные passwords/ACL и certs; deployment env/Compose входят в Python config archive. Архивы закрыты `umask 077`. Per-node secrets находятся в БД/NVS; полный backup не заменяет отдельную копию NVS устройств.

`backup:database` — отдельная Artisan-команда с собственной ротацией 7d; её наличие не закрывает backup конфигураций и Docker volumes. Порядок и границы восстановления — [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md), диагностика — [RUNBOOKS.md](RUNBOOKS.md).

## Еженедельное и ежемесячное обслуживание

- Проверять рост raw/aggregates, логов, DLQ, очередь команд, свободное место и результаты очистки. `telemetry_daily` и archive tables не имеют автоматического TTL.
- Проверять действующие DB retention jobs: миграции могут пропустить Timescale/pg_cron при отсутствии extension или ошибке.
- Проверять восстановление выбранного dump в изолированную БД; полный DR — на отдельном стенде. Логический dump вместе с WAL не образует физический PITR.
- Сверять обновления зависимостей через lockfiles и CI, выполнять Composer/NPM audit в контейнере. Не подменять deployment произвольным `composer update` / `npm update` на работающем сервере.
- Проверять MQTT ACL/пароли/TLS, токены сервисов и обратную связь от устройств. Открытый порт 8883 не подтверждает, что listener с TLS запущен.

## Обновление приложения

Развёртывание выполняется из выбранного и проверенного revision; build, миграции и health checks описаны в [FULL_STACK_DEPLOY_DOCKER.md](../04_BACKEND_CORE/FULL_STACK_DEPLOY_DOCKER.md).

В production основной путь — `make prod-check`, `make prod-up`, `make prod-migrate`, затем проверка readiness и логов. Сохраняйте существующий `APP_KEY` и secrets; `prod-seed` — отдельная bootstrap-операция. Повторно генерировать ключ при обычном deploy/restore нельзя.

Перед рестартом AE3 проверьте active tasks/commands и владение lease. После рестарта проверяйте recovery/reconcile, а не отправляйте повторную физическую дозу из-за отсутствия прогресса UI. Точные инцидентные процедуры — [RUNBOOKS.md](RUNBOOKS.md).

Добавление зон/нод проходит через Laravel API/UI и подтверждённый binding `config_report`. Увеличение числа экземпляров worker не заменяет проверку single-writer/fencing; ограничения одной инсталляции — [SINGLE_INSTANCE_SPOF_RUNBOOK.md](SINGLE_INSTANCE_SPOF_RUNBOOK.md).
