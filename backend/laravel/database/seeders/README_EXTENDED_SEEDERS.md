# Расширенные сидеры для проекта Hydro 2.0

## РЕФАКТОРИНГ 2025

Сидеры были полностью рефакторированы для улучшения:
- **Архитектуры**: Введены интерфейсы и базовые классы
- **Управления зависимостями**: Автоматическое разрешение зависимостей
- **Логирования**: Детальная статистика выполнения
- **Прогресс-баров**: Визуализация процесса сидирования
- **Валидации**: Проверка данных перед созданием
- **Чистоты**: Удалены устаревшие сидеры

### Новые возможности
- ✅ Базовый класс `BaseSeeder` с общей функциональностью
- ✅ Интерфейсы для типизации сидеров
- ✅ Группировка сидеров по назначению
- ✅ Автоматическая проверка зависимостей
- ✅ Прогресс-бары для долгих операций
- ✅ Детальная статистика выполнения

Этот набор расширенных сидеров создает полную и реалистичную базу данных для разработки и тестирования всех компонентов системы.

## Структура сидеров

### Базовые сидеры (всегда выполняются)
- `AdminUserSeeder` - создает административного пользователя
- `PresetSeeder` - создает пресеты для выращивания растений
- `PlantTaxonomySeeder` - создает базовую таксономию растений

### Расширенные сидеры (выполняются в development/local окружении)

#### 1. ExtendedUsersSeeder
Создает разнообразных пользователей с разными ролями:
- Администраторы (3 пользователя)
- Операторы (6 пользователей)
- Наблюдатели (4 пользователя)
- Тестовые пользователи (2 пользователя)

**Все пользователи имеют пароль: `password`**

#### 2. ExtendedGreenhousesZonesSeeder
Создает:
- 5 теплиц разных типов (производственная, исследовательская, сезонная, обучающая, демонстрационная)
- Множество зон для каждой теплицы с разными статусами (RUNNING, PAUSED, STOPPED)
- Настройки зон, профили оборудования, возможности

#### 3. ExtendedNodesChannelsSeeder
Создает:
- Узлы устройств для каждой зоны (3-6 узлов в зависимости от статуса зоны)
- Каналы для каждого узла (датчики и актуаторы)
- Непривязанные узлы в разных состояниях жизненного цикла

#### 4. ExtendedInfrastructureSeeder
Создает:
- Инфраструктуру зон (резервуары, насосы, панели освещения и т.д.)
- Привязки каналов к оборудованию

#### 5. ExtendedRecipesCyclesSeeder
Создает:
- 5 различных рецептов выращивания с фазами
- Экземпляры рецептов в активных зонах
- Циклы выращивания для всех зон

#### 6. ExtendedPlantsSeeder
Расширяет данные растений:
- Версии цен за последние 6 месяцев
- Статьи затрат
- Цены продажи
- Связи с рецептами

#### 7. ExtendedTelemetrySeeder
Создает:
- Исторические данные телеметрии за последние 3 дня (интервал 15 минут)
- Последние значения телеметрии для всех зон
- Реалистичные значения с дневными колебаниями

#### 8. ExtendedCommandsSeeder
Создает:
- Команды за последние 30 дней для активных зон
- Разные типы команд (DOSE, IRRIGATE, SET_LIGHT, SET_CLIMATE, READ_SENSOR, CALIBRATE, PUMP_CONTROL)
- Команды с разными статусами (QUEUED, SENT, ACCEPTED, DONE, FAILED, TIMEOUT, SEND_FAILED)

#### 9. ExtendedAlertsEventsSeeder
Создает:
- Алерты за последние 60 дней с разными типами и статусами
- События зон за последние 30 дней

#### 10. ExtendedAIPredictionsSeeder
Создает:
- Прогнозы параметров за последние 7 дней
- Симуляции для каждой зоны
- Параметры моделей (growth_prediction, ph_control, ec_control, climate_control)

#### 11. ExtendedHarvestsSeeder
Создает:
- Урожаи для завершенных циклов
- Исторические урожаи
- Аналитику рецептов

#### 12. ExtendedLogsSeeder
Создает:
- Системные логи за последние 7 дней
- Логи узлов
- AI логи
- Логи планировщика

#### 13. ExtendedGrowStagesSeeder
Создает:
- Шаблоны стадий роста (Посадка, Укоренение, Проращивание, Вегетативная, Цветение, Плодоношение, Сбор)
- Маппинг стадий к рецептам

#### 14. ExtendedZoneCyclesSeeder
Создает:
- Циклы зон (GROWTH_CYCLE, MAINTENANCE_CYCLE, CLEANING_CYCLE)
- Разные статусы циклов (active, finished, aborted)

#### 15. ExtendedZonePidConfigsSeeder
Создает:
- PID конфигурации для pH и EC для каждой зоны
- Реалистичные параметры PID регуляторов

#### 16. ExtendedPendingAlertsSeeder
Создает:
- Ожидающие алерты в разных статусах (pending, failed, dlq)
- Алерты от разных источников (biz, infra)

#### 17. ExtendedUnassignedNodeErrorsSeeder
Создает:
- Ошибки непривязанных узлов
- Ошибки с разными уровнями серьезности

#### 18. ExtendedArchivesSeeder
Создает:
- Архивные команды (commands_archive)
- Архивные события зон (zone_events_archive)
- Архивные ошибки узлов (unassigned_node_errors_archive)

#### 19. ExtendedAggregatorStateSeeder
Инициализирует:
- Состояние агрегатора телеметрии (1m, 1h, daily)
- Последние обработанные временные метки

#### 20. ExtendedTelemetryAggregatedSeeder
Создает:
- Агрегированную телеметрию по 1 минуте (за 3 дня)
- Агрегированную телеметрию по 1 часу (за 14 дней)
- Дневную агрегированную телеметрию (за 30 дней)

#### 21. ExtendedPlantRelationsSeeder
Создает:
- Связи растений с зонами (plant_zone)
- Связи растений с рецептами (plant_recipe)
- Циклы растений (plant_cycles)

#### 22. ExtendedInfrastructureAssetsSeeder
Создает:
- Глобальный каталог типов оборудования (PUMP, MISTER, TANK_NUTRIENT, LIGHT, VENT, HEATER и т.д.)

## Использование

### Запуск всех расширенных сидеров

```bash
php artisan db:seed
```

### Запуск отдельных сидеров

```bash
# Пользователи
php artisan db:seed --class=ExtendedUsersSeeder

# Теплицы и зоны
php artisan db:seed --class=ExtendedGreenhousesZonesSeeder

# Узлы и каналы
php artisan db:seed --class=ExtendedNodesChannelsSeeder

# И так далее...
```

### Запуск группы сидеров

```bash
# Запуск только инфраструктуры
php artisan tinker --execute="app(Database\Seeders\DatabaseSeeder::class)->runGroup('infrastructure');"

# Запуск только операционных данных
php artisan tinker --execute="app(Database\Seeders\DatabaseSeeder::class)->runGroup('operational_data');"
```

### Очистка и повторное заполнение

```bash
# Очистить базу данных и запустить миграции
php artisan migrate:fresh

# Запустить все сидеры
php artisan db:seed
```

### Диагностика сидеров

```bash
# Проверить статус всех сидеров
php artisan tinker --execute="
\$factory = app(App\Database\Seeders\SeederFactory::class);
\$seeders = [
    'ExtendedUsersSeeder',
    'ExtendedGreenhousesZonesSeeder',
    'ExtendedNodesChannelsSeeder',
];
\$results = \$factory->validateAllDependencies(\$seeders);
print_r(\$results);
"
```

## Статистика создаваемых данных

После выполнения всех расширенных сидеров создается:

- **Пользователи**: ~15 пользователей
- **Типы оборудования**: ~10 типов
- **Теплицы**: 5 теплиц
- **Зоны**: ~20-25 зон
- **Узлы**: ~60-80 узлов
- **Каналы**: ~200-300 каналов
- **Инфраструктура зон**: ~100-150 записей
- **Привязки каналов**: ~50-100 привязок
- **Рецепты**: 5 рецептов с фазами
- **Шаблоны стадий**: 7 шаблонов
- **Маппинг стадий**: ~15-25 маппингов
- **Циклы зон**: ~30-50 циклов
- **PID конфигурации**: ~40-50 конфигураций
- **Циклы выращивания**: ~30-50 циклов
- **Растения**: 2+ растения
- **Связи растений**: ~20-30 связей
- **Телеметрия**: ~50,000-100,000 samples
- **Агрегированная телеметрия**: ~10,000-20,000 записей
- **Команды**: ~5,000-10,000 команд
- **Алерты**: ~500-1,000 алертов
- **Ожидающие алерты**: ~10-30 алертов
- **События**: ~3,000-5,000 событий
- **Ошибки узлов**: ~10-20 ошибок
- **Прогнозы**: ~200-300 прогнозов
- **Симуляции**: ~50-100 симуляций
- **Урожаи**: ~30-50 урожаев
- **Логи**: ~10,000-20,000 записей
- **Архивные данные**: ~300-500 записей

## Зависимости между сидерами

Сидеры должны выполняться в следующем порядке:

1. `PresetSeeder` (базовый)
2. `PlantTaxonomySeeder` (базовый)
3. `ExtendedUsersSeeder`
4. `ExtendedInfrastructureAssetsSeeder` (независимый)
5. `ExtendedGreenhousesZonesSeeder` (требует PresetSeeder)
6. `ExtendedNodesChannelsSeeder` (требует ExtendedGreenhousesZonesSeeder)
7. `ExtendedInfrastructureSeeder` (требует ExtendedNodesChannelsSeeder и ExtendedInfrastructureAssetsSeeder)
8. `ExtendedRecipesCyclesSeeder` (требует ExtendedGreenhousesZonesSeeder)
9. `ExtendedGrowStagesSeeder` (требует ExtendedRecipesCyclesSeeder)
10. `ExtendedZoneCyclesSeeder` (требует ExtendedGreenhousesZonesSeeder)
11. `ExtendedZonePidConfigsSeeder` (требует ExtendedUsersSeeder и ExtendedGreenhousesZonesSeeder)
12. `ExtendedPlantsSeeder` (требует PlantTaxonomySeeder и ExtendedRecipesCyclesSeeder)
13. `ExtendedPlantRelationsSeeder` (требует ExtendedPlantsSeeder, ExtendedGreenhousesZonesSeeder, ExtendedRecipesCyclesSeeder)
14. `ExtendedTelemetrySeeder` (требует ExtendedNodesChannelsSeeder)
15. `ExtendedTelemetryAggregatedSeeder` (требует ExtendedNodesChannelsSeeder)
16. `ExtendedAggregatorStateSeeder` (независимый)
17. `ExtendedCommandsSeeder` (требует ExtendedNodesChannelsSeeder)
18. `ExtendedAlertsEventsSeeder` (требует ExtendedGreenhousesZonesSeeder)
19. `ExtendedPendingAlertsSeeder` (требует ExtendedGreenhousesZonesSeeder)
20. `ExtendedUnassignedNodeErrorsSeeder` (требует ExtendedNodesChannelsSeeder)
21. `ExtendedAIPredictionsSeeder` (требует ExtendedGreenhousesZonesSeeder)
22. `ExtendedHarvestsSeeder` (требует ExtendedRecipesCyclesSeeder)
23. `ExtendedLogsSeeder` (независимый)
24. `ExtendedArchivesSeeder` (требует ExtendedCommandsSeeder, ExtendedAlertsEventsSeeder, ExtendedUnassignedNodeErrorsSeeder)

`DatabaseSeeder` автоматически выполняет сидеры в правильном порядке.

## Особенности

- Все данные создаются с реалистичными значениями
- Учитывается статус зон при генерации данных
- Создаются связи между всеми сущностями
- Данные распределены во времени для реалистичности
- Используются `firstOrCreate` для предотвращения дублирования

## Окружения

Расширенные сидеры выполняются только в окружениях `local` и `development`.
В production они не выполняются автоматически.

Для выполнения в других окружениях используйте:

```bash
APP_ENV=production php artisan db:seed --class=ExtendedUsersSeeder
```

## Примечания

- Все пароли пользователей: `password`
- Email адреса имеют формат: `{role}@hydro.local`
- UID узлов и зон генерируются случайно
- Временные метки распределены реалистично
