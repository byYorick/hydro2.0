# Connection Status Component

Компонент для получения статуса соединений (WiFi, MQTT, RSSI).

## Описание

Общая логика получения статуса соединений для всех нод.

## Использование

```c
#include "connection_status.h"

connection_status_t status;
connection_status_get(&status);

if (status.wifi_connected) {
    // WiFi подключен
}
if (status.mqtt_connected) {
    // MQTT подключен
}
int8_t rssi = status.wifi_rssi;
```

## API

- `connection_status_get()` - получение текущего статуса соединений

