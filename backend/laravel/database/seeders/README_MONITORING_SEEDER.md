# MonitoringDataSeeder

Seeder для создания дополнительных данных для демонстрации системы мониторинга в Grafana dashboards.

## Описание

Создает:
- **События зон** (`zone_events`) - различные типы событий за последние 7 дней
- **Алерты** (`alerts`) - активные и решенные алерты для демонстрации

## Создаваемые данные

### События зон

Для каждой зоны создается по 2-3 события каждого типа за последние 7 дней:

- `PH_CORRECTION` - корректировка pH
- `EC_CORRECTION` - корректировка EC
- `IRRIGATION_START` - начало полива
- `IRRIGATION_STOP` - окончание полива
- `PHASE_TRANSITION` - переход между фазами рецепта
- `LIGHT_ON` - включение освещения
- `LIGHT_OFF` - выключение освещения

### Алерты

Создаются различные типы алертов:

- `PH_HIGH` / `PH_LOW` - отклонения pH
- `EC_HIGH` / `EC_LOW` - отклонения EC
- `TEMP_HIGH` / `TEMP_LOW` - отклонения температуры
- `HUMIDITY_HIGH` / `HUMIDITY_LOW` - отклонения влажности
- `WATER_LEVEL_LOW` - низкий уровень воды
- `NO_FLOW` - отсутствие потока воды
- `NODE_OFFLINE` - узел офлайн

Для каждой зоны:
- 1-3 активных алерта
- 2-5 решенных алертов за последние 7 дней

## Использование

### Запуск отдельно

```bash
docker exec backend-laravel-1 php artisan db:seed --class=MonitoringDataSeeder
```

### Автоматический запуск

Seeder автоматически вызывается в `DatabaseSeeder` после создания телеметрии:

```php
$this->call(TelemetrySeeder::class);
$this->call(MonitoringDataSeeder::class);
```

### Полное заполнение базы

```bash
# Очистить и заполнить все данные
docker exec backend-laravel-1 php artisan migrate:fresh --seed
```

## Проверка данных

После выполнения проверьте созданные данные:

```bash
docker exec backend-laravel-1 php artisan tinker --execute="
echo 'События: ' . App\Models\ZoneEvent::count() . PHP_EOL;
echo 'Алерты (всего): ' . App\Models\Alert::count() . PHP_EOL;
echo 'Алерты (активные): ' . App\Models\Alert::where('status', 'active')->count() . PHP_EOL;
"
```

## Интеграция с мониторингом

Созданные данные используются в Grafana dashboards:

- **Alerts Dashboard** - отображает активные и решенные алерты
- **Zone Telemetry Dashboard** - показывает события зон
- **System Overview** - общая статистика по алертам

## Примечания

- Seeder использует `firstOrCreate` для предотвращения дубликатов
- События распределены случайным образом за последние 7 дней
- Алерты создаются с реалистичными значениями и порогами
- Seeder безопасен для повторного запуска (не создает дубликаты)

