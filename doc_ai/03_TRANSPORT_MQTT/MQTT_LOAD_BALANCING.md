# MQTT_LOAD_BALANCING.md
# Полная архитектура распределения нагрузки MQTT в системе 2.0
# Multi‑Broker • Auto‑Failover • Node Balancing • High Availability • Traffic Sharding

Документ описывает систему распределения нагрузки MQTT между несколькими брокерами,
повышающую отказоустойчивость и масштабируемость тепличного комплекса 2.0.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

# 1. Зачем нужен Load Balancing MQTT

С увеличением числа узлов ESP32 (50–500+), телеметрии, команд и AI‑моделей,
единый MQTT‑брокер может стать узким местом.

MQTT Load Balancing 2.0 позволяет:

- распределять узлы по разным брокерам,
- снижать нагрузку на CPU/IO,
- избежать пиковых перегрузок,
- обеспечить отказоустойчивость,
- увеличить масштабируемость кластера.

---

# 2. Архитектура MQTT LB 2.0

Система состоит из:

```
Primary Broker (mqtt1)
Secondary Broker (mqtt2)
Tertiary Broker (mqtt3)
Broker Registry
Node Assignment Engine
Failover Engine
Python Scheduler Multi‑Broker Connector
Health Monitor
```

---

# 3. Варианты балансировки

## 3.1. Static Sharding (по node_id)
```
node_id % broker_count
```

## 3.2. Dynamic Load Sharding
Python Scheduler распределяет узлы в реальном времени:

- по нагрузке,
- по количеству пакетов,
- по задержкам.

## 3.3. Priority‑Based Distribution
Критичные зоны → отдельно стоящие брокеры.

---

# 4. Node Assignment Engine

Алгоритм:

```
fetch all brokers
calculate load index per broker
assign node to broker with minimal index
save mapping to DB
push new broker_url to node via config topic
```

Load Index учитывает:

- текущие соединения,
- сообщения/сек,
- CPU usage брокера,
- network latency.

---

# 5. Переключение узлов между брокерами

Процесс:

1. Python Scheduler генерирует:
```
nodes/<id>/config/update
{
 "mqtt_broker": "mqtt2.example"
}
```

2. Узел:
- сохраняет новый адрес в NVS,
- перезапускает MQTT,
- отправляет STATUS на новый брокер.

3. Backend обновляет mapping.

---

# 6. Multi‑Broker Python Scheduler

Scheduler поддерживает подключения к нескольким брокерам одновременно:

```
mqtt_clients = {
 "mqtt1": client1,
 "mqtt2": client2,
 "mqtt3": client3
}
```

Каждый клиент:

- принимает телеметрию узлов,
- отправляет команды конкретным узлам,
- синхронизирует offline‑очередь.

---

# 7. Синхронизация данных между брокерами

### 7.1. Telemetry Merge Layer
Все сообщения со всех брокеров попадают в общий поток.

### 7.2. Command Routing
Команды отправляются только на брокер, к которому привязан узел.

### 7.3. Event Aggregation
События всех брокеров идут в одно место:

```
zone_events
```

---

# 8. Автоматический Failover

Если брокер недоступен:

1. Python обнаруживает:
 - отсутствуют сообщения,
 - нет ACK команд,
 - tcp disconnect.

2. Запускается Failover Engine:

```
mark broker as DOWN
move nodes to healthy brokers
regenerate config updates
```

3. Узлы получают новый адрес:

```
nodes/<id>/config/update
```

4. Backend помечает брокер:

```
status = offline
```

---

# 9. Health Monitoring брокеров

Отслеживаются:

- ping latency,
- heap/CPU (если EMQX),
- number of connections,
- packet rate,
- disconnects,
- uptime,
- retained messages.

Статусы:

```
GOOD / DEGRADED / CRITICAL / OFFLINE
```

---

# 10. High Availability режим (HA)

Поддерживается схема:

```
mqtt1 — primary
mqtt2 — hot standby
mqtt3 — optional
```

Репликация:

- сессии,
- retained топики,
- правила ACL (копирование),
- пользовательские параметры.

---

# 11. Резервные режимы

## 11.1. Local Fallback Broker
ESP32 может иметь локальный резервный MQTT:

- включается при отсутствии сети,
- доступен на локальном Wi‑Fi.

## 11.2. Offline Queue на узле
Узел сохраняет данные до 50 пакетов:

```
telemetry buffer
error buffer
status buffer
```

При восстановлении:
- отправляется всё накопленное.

---

# 12. UI Load Balancing Dashboard

Панель отображает:

- список брокеров,
- текущее количество узлов на каждом,
- статус брокера,
- нагрузку в сообщениях/сек,
- карту распределения зон,
- историю failover событий.

---

# 13. AI Integration

AI анализирует:

- узлы с высокой активностью,
- узлы с плохим сигналом,
- узлы с частыми командами,
- перегруженные брокеры.

AI может предложить:

- перераспределить узлы,
- выделить отдельный брокер,
- объединить группы зон,
- изменить стратегию распределения.

ИИ не может:

- отключать failover,
- снижать уровень безопасности,
- назначать узлам несуществующие брокеры.

---

# 14. Чек‑лист перед релизом MQTT LB 2.0

1. Multi‑Broker работает? 
2. Telemetry merge корректна? 
3. Commands routed правильно? 
4. Failover работает без потерь? 
5. Node reassignment корректен? 
6. Mapping хранится в БД? 
7. UI dashboard отображает данные? 
8. AI правильно анализирует нагрузку? 

---

# Конец файла MQTT_LOAD_BALANCING.md
