---
name: hydro2-postgres-recovery
description: "Диагностика PostgreSQL/TimescaleDB и проверка backup/recovery Hydro 2.0. Используй при restore, PITR, WAL, retention и проблемах БД; различай логический dump и физическую base backup, сохраняй APP_KEY и отдельный тестовый контур."
license: MIT
metadata:
  type: workflow
  lifecycle: active
  version: "0.1.0"
  upstream: postgres-pro
---

# PostgreSQL и восстановление Hydro 2.0

## Выбор контура

Прочитай [backup/recovery](../../../doc_ai/08_SECURITY_AND_OPS/BACKUP_AND_RECOVERY.md) и [retention](../../../doc_ai/05_DATA_AND_STORAGE/DATA_RETENTION_POLICY.md). Установи выбранный Compose-проект, версию PostgreSQL/TimescaleDB, имя БД и цель операции. Dev, hydro_test и realhw hydro_e2e — разные контуры.
Не выводи пароль, APP_KEY, node_secret, DSN с credentials или содержимое .env. Используй штатное соединение/контейнер и утверждённые переменные, а не пароль из примера.

## Диагностика

Начни с read-only состояния подключения, размера БД, pg_stat и схемы. Сверяй [snapshot](../../../schemas/automation_read_model_schema.json), не придумывай колонки.
EXPLAIN без ANALYZE показывает план. EXPLAIN ANALYZE действительно выполняет запрос; особенно для INSERT/UPDATE/DELETE это не read-only диагностика. Изменения схемы и индексов оформляй Laravel-миграциями, не CREATE INDEX вручную на стенде.

## Логическое восстановление

- postgres_backup.sh создаёт pg_dump -Fc; сначала проверь manifest, pg_restore --list и совместимость расширений.
- postgres_restore.sh удаляет и пересоздаёт DB_NAME. Для проверки выбери отдельный кластер/БД и исключи подключение к актуаторам. Убедись, что авторизация пользователя охватывает восстановление именно выбранной цели.
- Восстановленный APP_KEY сохраняется. Отсутствие исходного ключа — причина искать его копию; не генерируй замену при восстановлении существующих данных.
- После restore проверь данные, расширения, версии приложения и восстановленные active tasks. Запуск AE3/scheduler и переключение трафика выполняются отдельно в согласованном объёме.

## Физический PITR

Нужны физическая base backup и непрерывная цепочка WAL с подходящей timeline. Логический pg_dump не служит базой для WAL replay.
Для PostgreSQL 16 используются restore_command, recovery target и recovery.signal. recovery.conf устарел. Опция --wal-dir текущего restore-скрипта только выводит предупреждение, PITR не реализует.
Обычный tar работающего PGDATA не гарантирует согласованную копию. Не удаляй WAL, от которых зависит сохраняемая base backup.

## Результат

Зафиксируй тип копии, выбранную цель, фактические проверки и измеренные RPO/RTO. Цель ≤30 минут не выдавай за подтверждённый результат. Чтение скрипта и наличие WAL не равны успешному восстановлению.

- [Runbooks](../../../doc_ai/08_SECURITY_AND_OPS/RUNBOOKS.md)
- [PostgreSQL 16: PITR](https://www.postgresql.org/docs/16/continuous-archiving.html)
- [Источники адаптации](../../../tools/skills/project-skills.json)

Метод диагностики адаптирован из PostgreSQL Pro (Jeffallan/claude-skills, MIT); детали recovery сверяются с документацией PostgreSQL и кодом Hydro.
