# Сидеры телеметрии для миниграфиков

## Описание

Сидеры для заполнения тестовыми данными телеметрии, необходимые для отображения миниграфиков на фронтенде.

## Доступные сидеры

### 1. TelemetrySeeder (основной)

Генерирует полный набор данных телеметрии:
- **Последние 24 часа**: каждые 5 минут (288 точек) - для детальных миниграфиков
- **Последние 7 дней**: каждый час (168 точек) - для средних периодов
- **Последние 30 дней**: каждые 6 часов (120 точек) - для длительных периодов

**Автоматически запускает агрегацию данных** после заполнения.

### 2. TelemetryMiniGraphSeeder (быстрый)

Генерирует только данные для миниграфиков:
- **Последние 24 часа**: каждые 5 минут (288 точек)

Идеально для быстрого тестирования миниграфиков без генерации большого объема данных.

## Использование

### Полное заполнение (рекомендуется)

```bash
# В Docker контейнере
docker exec backend-laravel-1 php artisan db:seed --class=TelemetrySeeder

# Или через DatabaseSeeder (включает все сидеры)
docker exec backend-laravel-1 php artisan db:seed
```

### Только для миниграфиков (быстро)

```bash
docker exec backend-laravel-1 php artisan db:seed --class=TelemetryMiniGraphSeeder
```

### Очистка и повторное заполнение

```bash
# Очистить существующие данные
docker exec backend-laravel-1 php artisan tinker --execute="DB::table('telemetry_samples')->truncate(); DB::table('telemetry_last')->truncate(); DB::table('telemetry_agg_1m')->truncate(); DB::table('telemetry_agg_1h')->truncate();"

# Заполнить заново
docker exec backend-laravel-1 php artisan db:seed --class=TelemetrySeeder
```

## Генерируемые метрики

Сидеры автоматически определяют метрики из каналов узлов и генерируют данные для:

- **PH** (pH): базовое значение 5.8, вариация ±0.3
- **EC** (электропроводность): базовое значение 1.5, вариация ±0.2
- **TEMPERATURE** (температура): базовое значение 22.0°C, вариация ±3.0
- **HUMIDITY** (влажность): базовое значение 60%, вариация ±10%
- **WATER_LEVEL** (уровень воды): базовое значение 50%, вариация ±15%
- **FLOW_RATE** (скорость потока): базовое значение 2.0, вариация ±0.5

## Особенности генерации

1. **Реалистичные паттерны**: данные генерируются с использованием синусоид для создания реалистичных трендов и циклов
2. **Дневные циклы**: учитываются суточные колебания параметров
3. **Случайный шум**: добавляется небольшой случайный шум для реалистичности
4. **Автоматическая агрегация**: после заполнения запускается команда `telemetry:aggregate` для создания агрегированных данных

## Проверка данных

После заполнения проверьте количество записей:

```bash
# Количество raw samples
docker exec backend-laravel-1 php artisan tinker --execute="echo 'Samples: ' . DB::table('telemetry_samples')->count();"

# Количество агрегированных данных (1 минута)
docker exec backend-laravel-1 php artisan tinker --execute="echo 'Agg 1m: ' . DB::table('telemetry_agg_1m')->count();"

# Количество агрегированных данных (1 час)
docker exec backend-laravel-1 php artisan tinker --execute="echo 'Agg 1h: ' . DB::table('telemetry_agg_1h')->count();"
```

## Устранение проблем

### Данные не отображаются на графиках

1. Проверьте, что зоны и узлы созданы:
```bash
docker exec backend-laravel-1 php artisan tinker --execute="echo 'Zones: ' . App\Models\Zone::count(); echo ' Nodes: ' . App\Models\DeviceNode::count();"
```

2. Проверьте, что каналы настроены:
```bash
docker exec backend-laravel-1 php artisan tinker --execute="echo 'Channels: ' . App\Models\NodeChannel::where('type', 'sensor')->count();"
```

3. Запустите агрегацию вручную:
```bash
docker exec backend-laravel-1 php artisan telemetry:aggregate --from="$(date -d '30 days ago' '+%Y-%m-%d %H:%M:%S')" --to="$(date '+%Y-%m-%d %H:%M:%S')"
```

### Медленная генерация данных

Для больших объемов данных процесс может занять несколько минут. Используйте `TelemetryMiniGraphSeeder` для быстрого тестирования.

## Интеграция с DatabaseSeeder

Сидер `TelemetrySeeder` автоматически вызывается в `DatabaseSeeder` при запуске в development окружении:

```php
if (app()->environment('local', 'development')) {
    $this->call(DemoDataSeeder::class);
    $this->call(TelemetrySeeder::class);
}
```
