# AGENTS.md
# Правила для ИИ-агентов (backend/laravel)

**Область:** `backend/laravel/*`  
**Канон репозитория:** корневой `AGENTS.md`. Этот файл уточняет Laravel/Inertia/тесты; не переопределяет SoT.

## Версии (authoritative)

PHP 8.2.29 · Laravel 12 · Inertia 2 · Vue 3 · Tailwind 3 · PHPUnit 11

## Пайплайн и границы

- Laravel **не** публикует MQTT и не ходит в брокер. Команды: scheduler-dispatch → AE3 → `history-logger` `POST /commands` → MQTT.
- Схема БД — только Laravel-миграции; ручной DDL запрещён.
- `env()` только в `config/*.php`; в коде — `config('…')`.
- Новые Python-сервисы / AE3 `task_type` / authority document types — **запрещены без явного запроса**.
- Не ломать пайплайн `ESP32 → MQTT → Python → PostgreSQL → Laravel → Vue`. Смена API/Inertia props — сразу Vue.
- Роли/`auth` не менять без явной нужды и тестов.

## Eloquent, HTTP, Artisan

- Eloquent + relationships, не `DB::`; eager load против N+1.
- Валидация — Form Request, не inline в контроллере.
- Named routes + `route()`, не хардкод URL.
- Тяжёлое — `ShouldQueue`. ML/симуляцию в Laravel не встраивать.
- Новые файлы — `php artisan make:` + `--no-interaction`.
- Constructor property promotion, явные return types, `{}` даже для однострочных if.
- PHPDoc вместо inline-комментов. Enum keys — TitleCase.
- Перед финализацией: `vendor/bin/pint --dirty` (внутри контейнера `laravel`).

## Laravel 12 структура

- middleware / exceptions / routing — `bootstrap/app.php`
- providers — `bootstrap/providers.php`
- нет `app/Console/Kernel.php`; команды auto-register из `app/Console/Commands/`

## Inertia / Vue

- Страницы в `resources/js/Pages`. Сервер: `Inertia::render()`.
- `<script setup>`, один root-элемент, навигация `<Link>` / `router.visit()`.
- Inertia v2: polling, prefetch, deferred props (со skeleton empty state), lazy.
- Формы: `<Form>` или `useForm`.
- Tailwind **только v3**; gap-утилиты вместо margin-списков.
- Shared-компоненты зоны переиспользуются в wizard и zone edit.
- Manual-step controls — только из `allowed_manual_steps`.

## Тесты

- PHPUnit (не Pest). Каждое изменение — тест; узкий `--filter=` / файл.
- Фабрики моделей; при смене column в migration включать все предыдущие атрибуты.
- Не удалять тесты без согласования.

## Docker

Команды `artisan` / `composer` / `npm` — **внутри** контейнера `laravel`:

```bash
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test --filter=TestClassName
```
