# Оптимизация Telemetry в Zone Event Ledger

## Проблема

`NodeTelemetryUpdated` событие записывается в `zone_events` при каждом обновлении телеметрии. При частоте обновлений каждые 3-5 секунд это создает:

- **~12,000-28,800 событий в день** для одной зоны с 10 нодами
- **~360,000-864,000 событий в месяц** для одной зоны
- При 10 зонах: **~3.6-8.6 миллионов событий в месяц**

Это может привести к:
- Раздуванию таблицы `zone_events`
- Медленным запросам catch-up
- Увеличению нагрузки на БД
- Проблемам с retention

---

## Решения

### Вариант 1: Запись только значимых изменений (Рекомендуется)

Записывать телеметрию в ledger только при:
- Значимых изменениях значения (больше порога)
- Изменении состояния (например, переход из "норма" в "критическое")
- Агрегированных обновлениях (например, раз в минуту)

#### Реализация

```php
<?php

namespace App\Events;

use App\Models\DeviceNode;
use App\Services\EventSequenceService;
use App\Services\TelemetryLedgerFilter;
use App\Traits\RecordsZoneEvent;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class NodeTelemetryUpdated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels, RecordsZoneEvent;

    // ... existing code ...

    /**
     * Записывает событие в zone_events только при значимых изменениях.
     */
    public function broadcasted(): void
    {
        // Получаем узел для определения zone_id
        $node = DeviceNode::find($this->nodeId);
        if (!$node || !$node->zone_id) {
            return;
        }

        // Проверяем, нужно ли записывать это событие в ledger
        $filter = app(TelemetryLedgerFilter::class);
        if (!$filter->shouldRecord($node->zone_id, $this->metricType, $this->value)) {
            // Не записываем - это незначимое изменение
            return;
        }

        // Записываем только значимые изменения
        $this->recordZoneEvent(
            zoneId: $node->zone_id,
            type: 'telemetry_updated',
            entityType: 'telemetry',
            entityId: $this->nodeId,
            payload: [
                'channel' => $this->channel,
                'metric_type' => $this->metricType,
                'value' => $this->value,
                'ts' => $this->timestamp,
            ],
            eventId: $this->eventId,
            serverTs: $this->serverTs
        );
    }
}
```

#### Сервис фильтрации

```php
<?php

namespace App\Services;

use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;

class TelemetryLedgerFilter
{
    // Пороги значимых изменений для разных метрик
    private const THRESHOLDS = [
        'PH' => 0.1,           // Изменение pH на 0.1
        'EC' => 0.2,           // Изменение EC на 0.2 mS/cm
        'TEMPERATURE' => 0.5,  // Изменение температуры на 0.5°C
        'HUMIDITY' => 2.0,     // Изменение влажности на 2%
        'CO2' => 50,           // Изменение CO2 на 50 ppm
        'LIGHT_INTENSITY' => 100,          // Изменение освещенности на 100 lux
    ];

    // Минимальный интервал между записями (в секундах)
    private const MIN_INTERVAL_SECONDS = 60; // 1 минута

    /**
     * Проверяет, нужно ли записывать событие телеметрии в ledger.
     */
    public function shouldRecord(int $zoneId, string $metricType, float $value): bool
    {
        $cacheKey = "telemetry_last_recorded:zone_{$zoneId}:{$metricType}";
        
        // Получаем последнее записанное значение
        $lastRecorded = Cache::get($cacheKey);
        
        if ($lastRecorded === null) {
            // Первое значение для этой метрики - записываем
            $this->updateCache($cacheKey, $value);
            return true;
        }

        $lastValue = $lastRecorded['value'];
        $lastTimestamp = $lastRecorded['timestamp'];

        // Проверяем интервал времени
        $timeSinceLastRecord = time() - $lastTimestamp;
        if ($timeSinceLastRecord < self::MIN_INTERVAL_SECONDS) {
            // Слишком часто - не записываем
            return false;
        }

        // Проверяем значимость изменения
        $threshold = self::THRESHOLDS[$metricType] ?? 0.0;
        $change = abs($value - $lastValue);
        
        if ($change < $threshold) {
            // Изменение незначимо - не записываем
            return false;
        }

        // Значимое изменение - записываем
        $this->updateCache($cacheKey, $value);
        return true;
    }

    private function updateCache(string $cacheKey, float $value): void
    {
        Cache::put($cacheKey, [
            'value' => $value,
            'timestamp' => time(),
        ], now()->addHours(24));
    }
}
```

---

### Вариант 2: Исключить telemetry из ledger

Телеметрия доступна через:
- **Snapshot** (`latest_telemetry_per_channel`)
- **WebSocket stream** (real-time обновления)
- **Telemetry API** (исторические данные)

Ledger используется только для:
- Команд (command_status)
- Алертов (alert_created, alert_updated)
- Изменений устройств (device_status, node_config_updated)
- Изменений зоны (zone_updated)

#### Реализация

```php
<?php

namespace App\Events;

class NodeTelemetryUpdated implements ShouldBroadcast
{
    // ... existing code ...

    /**
     * НЕ записывает телеметрию в zone_events.
     * Телеметрия доступна через snapshot и WebSocket stream.
     */
    public function broadcasted(): void
    {
        // Телеметрия исключена из ledger для оптимизации
        // Используйте snapshot и WebSocket stream для получения телеметрии
        return;
    }
}
```

---

## Сравнение вариантов

| Критерий | Вариант 1 (Фильтрация) | Вариант 2 (Исключение) |
|----------|------------------------|------------------------|
| **События в ledger** | ~60-600/день (только значимые) | 0 |
| **Размер ledger** | Умеренный | Минимальный |
| **История изменений** | Частичная (значимые события) | Нет |
| **Catch-up для telemetry** | Возможен | Только через snapshot |
| **Сложность реализации** | Средняя | Низкая |
| **Точность reconciliation** | Частичная | Нет для telemetry |

---

## Рекомендация

**Для большинства случаев рекомендуем Вариант 2 (исключение)**:
- Телеметрия доступна через snapshot и WebSocket
- Ledger остается компактным и быстрым
- Catch-up для команд и алертов работает быстро
- Меньше сложности в коде

**Вариант 1 (фильтрация) подходит, если:**
- Нужна история значимых изменений телеметрии в ledger
- Требуется catch-up для критических изменений телеметрии
- Можно настроить пороги для каждой метрики

---

## Миграция

### Если выбрали Вариант 2 (исключение):

1. Обновить `NodeTelemetryUpdated::broadcasted()` - убрать запись в ledger
2. Опционально: архивировать существующие telemetry_updated события
3. Обновить документацию для Android-клиента

### Если выбрали Вариант 1 (фильтрация):

1. Создать `TelemetryLedgerFilter` сервис
2. Обновить `NodeTelemetryUpdated::broadcasted()` - использовать фильтр
3. Настроить пороги для каждой метрики
4. Протестировать на реальных данных

---

## Мониторинг

После внедрения оптимизации:

1. **Мониторить размер zone_events**
   ```sql
   SELECT 
       type,
       COUNT(*) as count,
       COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as percentage
   FROM zone_events
   WHERE created_at > NOW() - INTERVAL '1 day'
   GROUP BY type
   ORDER BY count DESC;
   ```

2. **Мониторить скорость catch-up**
   - Время ответа `/api/zones/{id}/events`
   - Размер gap в событиях

3. **Мониторить использование snapshot**
   - Частота запросов snapshot
   - Размер ответа snapshot

---

## Альтернативный подход: Агрегация

Вместо фильтрации можно агрегировать телеметрию:

- Записывать в ledger только агрегированные значения (min/max/avg) за период
- Период: 1-5 минут
- Это сохраняет информацию о трендах, но уменьшает количество событий

```php
// Пример: записывать только агрегаты за 5 минут
if (shouldAggregate($metricType)) {
    $aggregate = getAggregate($zoneId, $metricType, 5); // последние 5 минут
    if ($aggregate) {
        recordZoneEvent(...);
    }
}
```
