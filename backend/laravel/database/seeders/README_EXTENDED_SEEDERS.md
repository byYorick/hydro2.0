# Сидеры Hydro 2.0

Актуальная схема сидирования для разработки и тестов.

## Профили сидеров

Профиль задается через `HYDRO_SEED_PROFILE` (см. `backend/laravel/config/hydro.php`).

- `lite` (по умолчанию): быстрый, облегченный набор данных.
- `start`: только стартовые пользователи.
- `full`: полный исторический набор групп `DatabaseSeeder`.

## Что создает `lite`

`DatabaseSeeder -> LiteAutomationSeeder`

- 2 теплицы.
- 2 зоны в каждой теплице (всего 4 зоны).
- Для каждой зоны 5 устройств разных типов:
  - `climate`
  - `irrig`
  - `ph`
  - `light`
  - `water`
- Для каждой зоны создаются инфраструктурные привязки (`infrastructure_instances`, `channel_bindings`).
- Базовый рецепт + 2 фазы (day/night targets в `extensions`).
- Циклы: `RUNNING`, `PAUSED`, `PLANNED` + одна зона без активного цикла.
- Сильно урезанные операционные данные:
  - минимум `alerts`
  - минимум `commands`
  - минимум `telemetry_samples`

## Матрица использования

- Локальная разработка UI/API: `lite`
- Быстрый ручной smoke: `lite`
- Только доступы/логин: `start`
- Глубокая нагрузочная проверка legacy-набором: `full`
- E2E/CI: `testing`/`e2e` окружение + `AutomationEngineE2ESeeder` (подключается `DatabaseSeeder` автоматически)

## Команды

### 1) Полный сброс и облегченный набор (рекомендуется)

```bash
php artisan migrate:fresh --seed
```

### 2) Только стартовые пользователи

```bash
HYDRO_SEED_PROFILE=start php artisan db:seed
```

### 3) Полный legacy-набор

```bash
HYDRO_SEED_PROFILE=full php artisan migrate:fresh --seed
```

### 4) Явный запуск lite

```bash
HYDRO_SEED_PROFILE=lite php artisan db:seed
```

## Тестовые пользователи

Создаются `AdminUserSeeder`:

- `admin@example.com` / `password` (`admin`)
- `agronomist@example.com` / `password` (`agronomist`)
- `operator@example.com` / `password` (`operator`)
- `viewer@example.com` / `password` (`viewer`)

## Важно

- Для корректной изоляции тестов используйте `migrate:fresh --seed`.
- Не меняйте контракты таблиц вручную: только через миграции.
- При изменении структуры данных обновляйте `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`.
