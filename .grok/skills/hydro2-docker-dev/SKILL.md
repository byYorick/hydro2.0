---
name: hydro2-docker-dev
description: "Настройка и диагностика dev Docker Compose Hydro 2.0: core, профили obs/sim/ml, build, порты и readiness. Используй при проблемах контейнеров и локального запуска; сохраняй существующий стек, данные и секреты."
license: Apache-2.0
metadata:
  type: workflow
  lifecycle: active
  version: "0.1.0"
  upstream: docker-local-dev
---

# Docker dev Hydro 2.0

## Сначала исследуй

Прочитай Makefile, backend/docker-compose.dev.yml, Dockerfile нужного сервиса и [quickstart](../../../QUICK_START.md). Проверь Docker/Compose и выбранный проект. Не переписывай стек по generic-шаблону.
В managed cloud следуй инструкции окружения для proxy/CA; сохраняй TLS verification и штатные proxy. Отсутствие видимого токена не означает отсутствие настроенной авторизации.

## Состав

Обычный make up поднимает core: mqtt, db, redis, laravel, mqtt-bridge, history-logger, automation-engine, telemetry-aggregator.
- make up-obs — Prometheus/Grafana/Alertmanager и exporters.
- make up-sim — digital-twin/node-sim-manager.
- make up-ml — feature-builder skeleton.
Опциональные профили включай по задаче, не как исправление неизвестной ошибки. mqtt-bridge — probe; его command/config routes удалены.

## Проверка по этапам

1. Начни со статической конфигурации. Не печатай полный docker compose config с раскрытыми env; используй --quiet, --services или --profiles.

```bash
docker compose -f backend/docker-compose.dev.yml config --quiet
docker compose -f backend/docker-compose.dev.yml config --services
```

2. Сверь mount, рабочий каталог, healthcheck и внутренние DNS имена. localhost внутри контейнера обозначает его самого; к БД обращаются по имени сервиса.
3. Сборку/запуск выполняй, когда задача включает проверку runtime. Для документации/skills достаточно соответствующих локальных проверок.
4. Если runtime уже поднят, выбери короткие логи нужного сервиса и health/readiness. Не сбрасывай данные при ошибке readiness.

make refresh, make reset-db, down -v и system prune с удалением данных не являются обычной диагностикой. Проверь, что запрос пользователя охватывает их эффекты; уже данное разрешение повторно не запрашивай.
Не добавляй production credentials, host paths другого разработчика или новые сервисы. Backend/tests выполняются в проектных контейнерах; firmware — в ESP-IDF.

## Результат

Укажи выбранные сервисы/профили, изменённые файлы, фактические проверки, причины неготовности. Не объявляй стенд готовым только потому, что Compose разбирается.

- [Потоки и границы сервисов](../../../doc_ai/ARCHITECTURE_FLOWS.md)
- [Источники адаптации](../../../tools/skills/project-skills.json)

Переработано из Docker Local Development (thienanblog/awesome-ai-agent-skills, Apache-2.0). Дата, commit и отличия записаны в манифесте.
