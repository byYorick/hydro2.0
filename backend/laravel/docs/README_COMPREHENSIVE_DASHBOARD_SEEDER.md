# ComprehensiveDashboardSeeder

Комплексный сидер для заполнения всех таблиц базы данных для проверки всех Grafana dashboards.

## Описание

Этот сидер создает данные для всех Grafana dashboards в системе:

1. **Alerts Dashboard** - алерты (активные и решенные)
2. **Automation Engine Service** - зоны, команды, статусы
3. **History Logger Service** - телеметрия (последние значения)
4. **Node Status** - узлы со статусами online/offline
5. **System Overview** - общая статистика по всем компонентам
6. **Zone Telemetry** - события зон
7. **Commands & Automation** - команды с различными статусами

## Создаваемые данные

### 1. Статусы узлов (Node Status Dashboard)

- Обновляет статусы узлов (online/offline)
- Устанавливает `last_seen_at`, `last_heartbeat_at`
- Добавляет метрики для online узлов:
  - `uptime_seconds` - время работы
  - `free_heap_bytes` - свободная память
  - `rssi` - сила сигнала WiFi

### 2. Команды (Automation Engine & Commands Dashboards)

Создает команды за последние 7 дней:
- **Типы команд:**
  - `DOSE` - дозирование (acid, base, nutrients, dilute)
  - `IRRIGATE` - полив
  - `SET_LIGHT` - управление освещением
  - `SET_CLIMATE` - управление климатом
  - `READ_SENSOR` - чтение сенсора

- **Статусы команд:**
  - `pending` - ожидает отправки (5%)
  - `sent` - отправлена (20%)
  - `ack` - подтверждена (70%)
  - `failed` - ошибка (5%)

- **Временные метки:**
  - `created_at` - время создания
  - `sent_at` - время отправки
  - `ack_at` - время подтверждения
  - `failed_at` - время ошибки

### 3. Алерты (Alerts Dashboard)

Создает различные типы алертов:

- **Типы алертов:**
  - `ph_high` / `ph_low` - отклонения pH
  - `ec_high` / `ec_low` - отклонения EC
  - `temp_high` / `temp_low` - отклонения температуры
  - `humidity_high` / `humidity_low` - отклонения влажности
  - `water_level_low` - низкий уровень воды
  - `no_flow` - отсутствие потока
  - `node_offline` - узел офлайн
  - `sensor_error` - ошибка сенсора
  - `pump_failure` - отказ насоса
  - `config_mismatch` - несоответствие конфигурации

- **Статусы:**
  - Активные алерты (1-5 на зону)
  - Решенные алерты (5-15 на зону за последние 7 дней)

### 4. События зон (Zone Telemetry Dashboard)

Создает события за последние 7 дней:

- **Типы событий:**
  - `PH_CORRECTION` - корректировка pH
  - `EC_CORRECTION` - корректировка EC
  - `IRRIGATION_START` / `IRRIGATION_STOP` - полив
  - `PHASE_TRANSITION` - переход между фазами
  - `LIGHT_ON` / `LIGHT_OFF` - управление освещением
  - `CLIMATE_ADJUSTMENT` - корректировка климата
  - `NODE_ONLINE` / `NODE_OFFLINE` - статусы узлов

- **Объем:** 15-40 событий в день на зону

### 5. Телеметрия (History Logger Dashboard)

Обновляет `telemetry_last` для всех метрик:

- **Метрики:**
  - `PH` - уровень pH
  - `EC` - электропроводность
  - `TEMPERATURE` - температура воздуха
  - `HUMIDITY` - влажность воздуха
  - `WATER_LEVEL` - уровень воды
  - `FLOW_RATE` - скорость потока

## Использование

### Запуск отдельно

```bash
docker exec backend-laravel-1 php artisan db:seed --class=ComprehensiveDashboardSeeder
```

### Автоматический запуск

Сидер автоматически вызывается в `DatabaseSeeder` после создания телеметрии:

```php
$this->call(TelemetrySeeder::class);
$this->call(ComprehensiveDashboardSeeder::class);
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
echo 'Команды: ' . App\Models\Command::count() . PHP_EOL;
echo 'Алерты (активные): ' . App\Models\Alert::where('status', 'active')->count() . PHP_EOL;
echo 'События: ' . App\Models\ZoneEvent::count() . PHP_EOL;
echo 'Узлы (online): ' . App\Models\DeviceNode::where('status', 'online')->count() . PHP_EOL;
"
```

## Интеграция с Grafana Dashboards

### Alerts Dashboard
- Отображает активные и решенные алерты
- Группировка по типам
- Временная шкала алертов

### Automation Engine Service
- Статус сервиса
- Команды по зонам и типам
- Ошибки и производительность

### Commands & Automation
- Статусы команд (pending/sent/ack/failed)
- Распределение по типам команд
- Временная шкала команд

### Node Status
- Статусы узлов (online/offline)
- Время последнего контакта
- Метрики узлов (uptime, memory, signal)

### History Logger Service
- Последние значения телеметрии
- Поток данных
- Ошибки обработки

### Zone Telemetry
- События зон
- Типы событий
- Временная шкала

### System Overview
- Общая статистика
- Статусы сервисов
- Сводные метрики

## Особенности

1. **Реалистичные данные:**
   - Временные метки распределены за последние 7 дней
   - Статусы команд соответствуют реальным сценариям
   - Алерты имеют реалистичные значения и пороги

2. **Безопасность:**
   - Использует `firstOrCreate` для предотвращения дубликатов
   - Проверяет наличие связанных данных перед созданием
   - Безопасен для повторного запуска

3. **Производительность:**
   - Batch вставки где возможно
   - Оптимизированные запросы
   - Минимальное количество обращений к БД

## Примечания

- Сидер требует наличия зон и узлов (создаются через `DemoDataSeeder`)
- Телеметрия должна быть создана через `TelemetrySeeder` для полной функциональности
- Данные распределены случайным образом для реалистичности
- Количество данных можно настроить в коде сидера
