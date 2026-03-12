# WIFI_CONNECTIVITY_ENGINE.md
# Полный движок Wi‑Fi подключений для ESP32 в архитектуре 2.0
# Multi-AP • Auto-Reconnect • Signal Health • Roaming • Diagnostics

Документ описывает всю логику Wi‑Fi работы узлов ESP32 в системе 2.0.

---

# 1. Цели Wi‑Fi движка

Wi‑Fi Engine отвечает за:

- автоматическое подключение к точкам доступа,
- устойчивую работу при слабом сигнале,
- повторные подключения,
- диагностику RSSI/качества сигнала,
- роуминг между точками,
- управление сетевыми параметрами,
- безопасное хранение Wi‑Fi данных.

---

# 2. Архитектура Wi‑Fi Engine

Компоненты:

```
wifi_manager.c
wifi_connect.c
wifi_reconnect.c
wifi_scan.c
wifi_health.c
wifi_events.c
wifi_config_nvs.c
```

---

# 3. Хранение данных в NVS

Данные хранятся в namespace `network`:

| key | значение |
|-----|----------|
| wifi_ssid | строка |
| wifi_pass | строка |
| wifi_backup_ssid | строка |
| wifi_backup_pass | строка |
| wifi_mode | station |
| mesh_enabled | false |

---

# 4. Процесс подключения

Алгоритм:

```
load_credentials_from_nvs()
start_wifi()
connect(ssid, pass)
wait(event_group_connected)
if not connected → retry
```

---

# 5. Auto‑Reconnect Strategy

Стратегии восстановления:

### 5.1. Immediate reconnect (до 5 раз)

```
retry_interval = 1 сек
```

### 5.2. Progressive Backoff

```
1 → 3 → 5 → 7 → 10 сек
```

### 5.3. Full reset после 3 минут неудач

```
esp_restart()
```

---

# 6. Multi‑AP Support

Узел поддерживает два набора параметров:

```
primary_ssid
backup_ssid
```

Алгоритм:

```
if rssi < -78 or connection fails:
 switch_to_backup()
```

---

# 7. Wi‑Fi Roaming

Если в зоне несколько точек доступа с одинаковым SSID:

Алгоритм:

```
scan networks
if stronger BSSID available:
 disconnect()
 connect(new_bssid)
```

Порог переключения:

```
difference ≥ 12 dB
```

---

# 8. Wi‑Fi Health Monitoring

Параметры:

- RSSI
- disconnect count
- reconnect attempts
- ping latency (опционально)
- MQTT reconnects

Возраст RSSI:

```
good = > -65
medium = -66 to -75
bad = < -76
```

---

# 9. Status Telemetry

Узел отправляет статус:

```
{
 "rssi": -69,
 "reconnects": 3,
 "uptime": 55200,
 "heap": 182000,
 "wifi_quality": "medium"
}
```

---

# 10. Wi‑Fi Events

События:

- WIFI_CONNECTED
- WIFI_DISCONNECTED
- WIFI_AUTH_FAIL
- WIFI_NO_SSID
- WIFI_CHANGED_AP
- WIFI_BAD_RSSI
- WIFI_RECOVERED

Все идут в MQTT `/status` и Python Scheduler.

---

# 11. Wi‑Fi Diagnostics

Узел собирает:

- сбросы Wi‑Fi
- ошибки DHCP
- падения MQTT
- плохой сигнал
- попытки подключения

Если много проблем → ALARM:

```
NODE_WIFI_UNSTABLE
```

---

# 12. Fail‑Safe режим

Если Wi‑Fi отсутствует ≥ 5 минут:

```
enable_limited_mode()
```

Отключается:

- dosing
- irrigation
- heater

Безопасные системы продолжают работать.

---

# 13. Wi‑Fi Scan Engine

Узел периодически:

```
scan every 5–10 minutes:
 gather RSSI table
```

Передаёт:

```
{
 "networks": [
 {"ssid":"gh1","rssi":-60},
 {"ssid":"gh1","rssi":-72}
 ]
}
```

---

# 14. MQTT Connectivity Integration

Если MQTT не отвечает:

Алгоритм:

```
mqtt_retries = 5
if failed:
 restart_wifi()
if still failed:
 switch_to_backup_ssid()
```

---

# 15. Оптимизация для энергоэффективности

Используется:

- Modem Sleep
- Light Sleep (опционально)

Режимы:

```
wifi_ps_type_t = WIFI_PS_MIN_MODEM
```

---

# 16. ИИ‑интеграция

AI получает:

- RSSI историю
- reconnect count
- wifi quality
- AP switches

И может предложить:

- поставить репитер,
- сменить расположение узла,
- заменить антенну,
- сменить канал AP.

ИИ НЕ может:

- отключать Wi‑Fi защиту,
- менять SSID без подтверждения.

---

# 17. Чек‑лист Wi‑Fi Engine перед релизом

1. Подключается к обоим AP? 
2. Работает автопереключение? 
3. Reconnect стабильный? 
4. MQTT стабильный? 
5. Статус отправляется? 
6. RSSI точный? 
7. Fail‑Safe режим работает? 
8. Диагностика корректная? 
9. Авторизация SSID работает? 
10. Нет утечек памяти? 

---

# Конец файла WIFI_CONNECTIVITY_ENGINE.md
