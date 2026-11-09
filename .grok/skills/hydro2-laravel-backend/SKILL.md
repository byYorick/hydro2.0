---
name: hydro2-laravel-backend
description: "Разработка Laravel 12 в Hydro 2.0: API, Eloquent, миграции, NodeConfig, scheduler-dispatch и Inertia/Vue. Применяй при правках backend/laravel; сохраняй владельцев схемы и команд, проверяй точечными тестами в Docker."
license: MIT
metadata:
  type: domain
  lifecycle: active
  version: "0.1.0"
  upstream: laravel-specialist
---

# Laravel backend Hydro 2.0

## Порядок работы

1. Прочитай корневой AGENTS.md, локальные инструкции и [backend-гайд](../../../doc_ai/10_AI_DEV_GUIDES/BACKEND_LARAVEL_PG_AI_GUIDE.md). Найди существующий аналог, маршруты, FormRequest, policy и потребителей ответа.
2. Laravel владеет схемой БД, конфигурацией и scheduler-dispatch. Автоматизацию исполняет AE3; MQTT-команды публикует history-logger. Не добавляй MQTT publish в controller/job.
3. Размещай валидацию, права и бизнес-логику по существующим паттернам. Сохраняй envelope API, роли и Inertia props; при изменении ответа сверяй Vue и Android.
4. Изменяй схему только Laravel-миграцией. Если поле читает AE3, одновременно обновляй manifest и snapshot по [read-model контракту](../../../doc_ai/04_BACKEND_CORE/LARAVEL_AE3_READ_MODEL_CONTRACT.md).
5. Для Eloquent проверь scope доступа к теплице/зоне, eager loading и число запросов. Не вводи новые архитектурные слои, Livewire или Horizon только потому, что их предлагает upstream.

## Проверка

Команды выполняются из корня репозитория в подготовленном dev-стеке:

```bash
docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan route:list --path=api
docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan test --filter=RelevantTest
```

RelevantTest замени существующим или добавленным целевым тестом. До тестов проверь отдельную test DB: не направляй RefreshDatabase на hydro_dev. Не запускай migrate:fresh, refresh/reset-db или миграции production в качестве проверки документации.
Для обратимой правки текста достаточно статической проверки; не вводи обязательный общий процент coverage.

## Результат

Укажи изменённый сценарий, затронутые API/таблицы/потребители, выполненные проверки и ограничения. Для защищённого контракта обнови doc_ai и Compatible-With.

## Опорные документы

- [API](../../../doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md)
- [Authority конфигурации](../../../doc_ai/04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md)
- [Источники и условия адаптации](../../../tools/skills/project-skills.json)

Переработано для Hydro 2.0 из Laravel Specialist (Jeffallan/claude-skills, MIT); commit и сохранённая лицензия указаны в манифесте.
