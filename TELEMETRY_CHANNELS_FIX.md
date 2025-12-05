# Node Telemetry Channels Fix

## Проблема

Нода `nd-clim-esp3278e` была зарегистрирована, но не имела каналов в базе данных:

```json
{
  "id": "nd-clim-esp3278e",
  "name": "nd-clim-esp3278e",
  "type": "climate",
  "status": "online",
  "fw_version": "v5.5.1",
  "config": null,
  "channels": []
}
```

Из-за этого телеметрия с ноды не публиковалась на фронтенд.

## Причина

При регистрации ноды через `node_hello` сообщение, метод `registerNodeFromHello()` в `NodeRegistryService` **не создавал** записи в таблице `node_channels` на основе массива `capabilities`, отправленного прошивкой.

## Решение

### 1. Автоматическое создание каналов при регистрации (для новых нод)

**Изменено:** `backend/laravel/app/Services/NodeRegistryService.php`

Добавлен новый метод `syncNodeChannelsFromCapabilities()`, который:
- Получает массив capabilities из сообщения `node_hello`
- Создает записи в `node_channels` для каждой capability
- Использует маппинг capability → channel configuration (type, metric, unit)

**Поддерживаемые capabilities:**
- `temperature` → sensor, TEMP_AIR, °C
- `humidity` → sensor, HUMIDITY, %
- `co2` → sensor, CO2, ppm
- `lighting` → actuator, LIGHT
- `ventilation` → actuator, VENTILATION
- `ph_sensor` → sensor, PH, pH
- `ec_sensor` → sensor, EC, mS/cm
- `pump_A`, `pump_B`, `pump_C`, `pump_D` → actuator, PUMP_*

Теперь при получении `node_hello`:
1. History Logger подписывается на `hydro/node_hello`
2. Пересылает сообщение в Laravel API `/api/nodes/register`
3. Laravel регистрирует ноду и **автоматически создает каналы** из capabilities
4. Отправляет NodeConfig через MQTT с новыми каналами

### 2. Artisan команда для существующих нод

**Создано:** `backend/laravel/app/Console/Commands/SyncNodeChannels.php`

Команда для синхронизации каналов у уже зарегистрированных нод:

```bash
# Синхронизировать каналы для конкретной ноды
php artisan nodes:sync-channels --node-uid=nd-clim-esp3278e

# Синхронизировать каналы для всех нод
php artisan nodes:sync-channels --all

# Режим dry-run (показать что будет сделано, без изменений)
php artisan nodes:sync-channels --node-uid=nd-clim-esp3278e --dry-run
```

Команда:
- Определяет capabilities на основе типа ноды (climate, ph, ec, pump)
- Создает отсутствующие каналы
- Пропускает уже существующие каналы
- Автоматически публикует обновленный NodeConfig через MQTT

### 3. Docker команда

Для запуска в Docker окружении:

```bash
cd /home/georgiy/esp/hydro/hydro2.0/backend
docker compose -f docker-compose.dev.yml exec laravel php artisan nodes:sync-channels --node-uid=nd-clim-esp3278e
```

## Результат

После запуска команды для `nd-clim-esp3278e`:

```
Found 1 node(s) to process
Processing node: nd-clim-esp3278e (type: climate)
  Capabilities: temperature, humidity, co2, lighting, ventilation
    ✓ Created channel 'temperature' (sensor, TEMP_AIR)
    ✓ Created channel 'humidity' (sensor, HUMIDITY)
    ✓ Created channel 'co2' (sensor, CO2)
    ✓ Created channel 'lighting' (actuator, LIGHT)
    ✓ Created channel 'ventilation' (actuator, VENTILATION)
  Summary: Created=5, Skipped=0
```

Теперь нода имеет каналы:

```json
{
  "id": "nd-clim-esp3278e",
  "channels": [
    {"channel": "temperature", "type": "sensor", "metric": "TEMP_AIR", "unit": "°C"},
    {"channel": "humidity", "type": "sensor", "metric": "HUMIDITY", "unit": "%"},
    {"channel": "co2", "type": "sensor", "metric": "CO2", "unit": "ppm"},
    {"channel": "lighting", "type": "actuator", "metric": "LIGHT"},
    {"channel": "ventilation", "type": "actuator", "metric": "VENTILATION"}
  ]
}
```

## Как телеметрия теперь работает

1. **Прошивка** публикует телеметрию через `node_telemetry_publish_sensor()`:
   ```c
   node_telemetry_publish_sensor("temperature", METRIC_TYPE_TEMPERATURE, 
                                 temperature_value, "°C", 0, false, true);
   ```

2. **MQTT** получает сообщение на топике:
   ```
   hydro/{gh_uid}/zn-{zone_id}/{node_uid}/telemetry
   ```

3. **History Logger** записывает в TimescaleDB:
   ```sql
   INSERT INTO telemetry (ts, node_id, channel, metric, value, unit)
   VALUES (NOW(), 2, 'temperature', 'TEMP_AIR', 22.5, '°C')
   ```

4. **Frontend** получает данные через WebSocket и REST API

## Проверка работы

1. Проверить каналы в UI:
   - Открыть страницу ноды
   - Должны отображаться все 5 каналов

2. Проверить телеметрию:
   ```bash
   # Подписаться на MQTT телеметрию
   docker compose -f docker-compose.dev.yml exec mqtt \
     mosquitto_sub -h localhost -t 'hydro/+/+/+/telemetry' -v
   ```

3. Проверить данные в базе:
   ```sql
   SELECT * FROM telemetry WHERE node_id = 2 ORDER BY ts DESC LIMIT 10;
   ```

## Для будущих нод

Новые ноды будут автоматически получать каналы при отправке `node_hello` с массивом `capabilities`. Ничего делать вручную не нужно.

Если нода регистрируется без каналов, используйте команду:
```bash
php artisan nodes:sync-channels --node-uid=<node-uid>
```

