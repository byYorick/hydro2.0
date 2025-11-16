# SYSTEM_FAILURE_RECOVERY.md
# Полный модуль восстановления после сбоев (Disaster & Failure Recovery)
# Node Failures • Controller Faults • Network Loss • Data Loss • Auto‑Recovery • Safe Modes

Документ описывает систему восстановления после сбоев (Failure Recovery) в архитектуре 2.0.
Она охватывает все уровни: ESP32 узлы, MQTT, Python Scheduler, Laravel, БД, AI, UI.

---

# 1. Общая идеология восстановления 2.0

Система построена по принципам:

- **Fail Operational** — при сбое система продолжает работать.
- **Fail Graceful** — сбой приводит к безопасному режиму.
- **Fail Safe** — безопасность растений и оборудования выше всего.
- **Auto Recovery** — автоматическое самовосстановление.
- **Layered Recovery** — 5 уровней восстановления.

---

# 2. Пять уровней восстановления

```
L1 — Node Recovery (узлы ESP32)
L2 — Network/MQTT Recovery
L3 — Python Scheduler Recovery
L4 — Backend (Laravel/API) Recovery
L5 — Database/Data Integrity Recovery
```

---

# 3. L1 — Node Recovery (ESP32)

Узел ESP32 проходит самодиагностику:

### 3.1. Wi-Fi Recovery
- reconnect с backoff
- смена AP
- reset wifi stack
- полная перезагрузка ESP32

### 3.2. MQTT Recovery
- reconnect 5 попыток
- restart wifi
- fallback в safe-mode

### 3.3. Sensor Recovery
- перезагрузка I2C
- переподключение сенсоров
- fallback на виртуальные данные (Twin)

### 3.4. Actuator Recovery
- остановка насосов/клапанов
- повторная попытка команд
- переход в safe mode

### 3.5. Memory Recovery
- очистка heap
- рестарт задач
- reboot при критическом уровне

### 3.6. Node Safe Mode
Включается при:
- работе без MQTT > 5 мин
- критичной памяти
- сбоях сенсоров
- перегреве CPU

Safe Mode блокирует:
- дозирование
- полив
- обогреватель

Оставляет:
- телеметрию
- статус
- watchdog

---

# 4. L2 — Network/MQTT Recovery

Осуществляется Python Scheduler:

### 4.1. MQTT Failure Detection
- нет ACK от узлов
- reconnect loops
- high latency
- publish errors

### 4.2. Recovery Strategy
1. reconnect MQTT 
2. restart connection 
3. restart scheduler process 
4. переключение на резервный MQTT-брокер (если настроен)

### 4.3. MQTT Load Balancing (опционально)
Если узлов много → система переключает узлы на разные брокеры.

---

# 5. L3 — Python Scheduler Recovery

Scheduler отвечает за:

- командную очередь,
- ретраи,
- симуляции,
- алерты,
- сохранение телеметрии.

### 5.1. Если Scheduler завис
Watchdog перезапускает процесс.

### 5.2. Если очередь команд повреждена
Система:
- очищает очередь,
- повторяет команды,
- помечает некорректные как failed.

### 5.3. Если проблема в логике
Автоматически активируется:
```
SCHEDULER_SAFE_MODE
```
В нём:
- запрещены новые команды,
- разрешена телеметрия,
- контроллеры — только наблюдение.

---

# 6. L4 — Backend (Laravel) Recovery

Laravel мониторит:

- доступность API,
- время выполнения,
- ошибки базы,
- rate limiting.

### Основные механизмы восстановления:

### 6.1. Horizon Queue Recovery
Если очередь зависла:
- horizon restart
- redis flush (если нужно)

### 6.2. API Protection
Если overload:
- включается API throttle
- переход в read‑only режим

### 6.3. Fallback UI Mode
UI работает на:
```
cached views + cached last data
```
Когда backend недоступен.

---

# 7. L5 — Database & Data Integrity Recovery

Postgres контролирует:

- целостность данных,
- журнал изменений,
- ошибки записи.

### 7.1. При повреждении данных
Алгоритм:

1. остановить запись,
2. создать дамп,
3. применить WAL recovery,
4. откат до последней стабильной точки,
5. восстановить сервисы.

### 7.2. Репликация
В 2.0 возможно использование:
- горячей реплики,
- резервного инстанса,
- локального cache storage.

---

# 8. Recovery для AI Engine

AI переходит в режим:
```
AI_RESTRICTED_MODE
```
если:

- нет данных,
- повреждены рецепты,
- нет связи с симулятором.

Ограничения:
- только чтение,
- прогнозы на основе последних данных,
- запрет генерации команд.

---

# 9. Recovery сценарии (готовые кейсы)

## 9.1. Пропал интернет
- узлы → safe mode
- backend → cached UI
- MQTT reconnect
- команды блокируются

## 9.2. Умер MQTT брокер
- Python → переключение на резервный
- узлы → несколько попыток reconnect
- fallback → local safe operations

## 9.3. Перегрузка Postgres
- Laravel → read‑only mode
- Python → локальное буферирование
- AI → restricted mode

## 9.4. Завис узел
- watchdog reboot
- повторная диагностика
- safe mode при повторном сбое

## 9.5. Ошибка сенсора pH
- замена на виртуальный (Twin)
- блок дозировки
- алерт

## 9.6. Ошибка нагревателя
- отключение нагрева
- переход климата в пассивный режим
- алерт

---

# 10. Recovery Logging

Каждое восстановление создаёт event:

```
SYSTEM_RECOVERY
NODE_REBOOT
NODE_SAFE_MODE
MQTT_RECOVERY
SCHEDULER_RESTART
AI_RESTRICTED
DB_ROLLBACK
```

---

# 11. Recovery UI

Панель отображает:

- дерево ошибок,
- текущее состояние системы,
- safe-mode уровни,
- утраченные данные,
- действия восстановления,
- прогноз AI о последствиях.

---

# 12. Правила для ИИ

ИИ может:
- рекомендовать recovery действия,
- предлагать улучшения безопасности,
- обнаруживать early‑warnings.

ИИ НЕ может:
- запускать recovery самостоятельно,
- отключать safety layers,
- перезагружать узлы или сервисы.

---

# 13. Чек‑лист перед релизом Recovery 2.0

1. Узлы корректно переходят в safe mode? 
2. MQTT восстанавливается? 
3. Scheduler перезапускается? 
4. Laravel переходит в read‑only? 
5. БД откатывается корректно? 
6. AI ограничивается? 
7. UI fallback работает? 
8. Recovery events логируются? 
9. Нет зависающих процессов? 
10. Все сценарии протестированы? 

---

# Конец файла SYSTEM_FAILURE_RECOVERY.md
