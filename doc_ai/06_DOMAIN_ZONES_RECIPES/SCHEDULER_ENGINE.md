# SCHEDULER_ENGINE.md
# Полная спецификация движка планировщика (Scheduler Engine) системы 2.0
# Python Async Event Loop, контроллеры зон, очередь команд, стратегии исполнения
# Инструкция для ИИ‑агентов и Python‑разработчиков

Этот документ описывает внутреннюю механику планировщика (scheduler) Python‑сервиса,
который управляет всеми контроллерами зон (pH, EC, Climate, Irrigation, Light),
работает с MQTT, очередями команд и взаимодействием с PostgreSQL.

Файл определяет:
- архитектуру event‑loop,
- обработку задач,
- расписание,
- параллелизм,
- ограничения,
- правила расширения для ИИ.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

# 1. Общая архитектура Scheduler Engine

Scheduler состоит из трёх основных подсистем:

```
┌────────────────────┐
│ MQTT Listener │ ← подписка на hydro/# 
└────────────────────┘
 ↓
┌────────────────────┐
│ Command Queue │ ← выполнение команд к узлам
└────────────────────┘
 ↓
┌────────────────────┐
│ Zone Controllers │ ← pH, EC, Climate, Irrigation, Light
└────────────────────┘
```

Scheduler работает в **asyncio event loop**, без потоков.

---

# 2. Основные задачи Event Loop

Event loop выполняет 4 фоновые задачи:

| Задача | Интервал | Описание |
|-----------------------------|----------|----------|
| `mqtt_listener()` | realtime | слушает MQTT и вызывает router |
| `run_zone_controllers()` | 5–10 сек | запускает pH/EC/Climate/etc |
| `run_command_dispatcher()` | 0.5–2 сек| отправляет команды MQTT‑узлам |
| `sync_housekeeping()` | 60 сек | обновляет статус зон/узлов |

Все задачи выполняются параллельно через `asyncio.gather`.

---

# 3. MQTT Listener (asynchronous)

```python
async def mqtt_listener():
 async with Client(MQTT_HOST, MQTT_PORT) as client:
 await client.subscribe("hydro/#")
 async for message in client.unfiltered_messages():
 await mqtt_router.handle(message.topic, message.payload)
```

### Требования:

- никакой логики обработки внутри listener;
- полная маршрутизация делается в mqtt_router;
- listener работает вечно и автоматически переподключается.

ИИ‑агент может:
- улучшать reconnect‑логику,
- добавлять метрики.

ИИ‑агент не может:
- изменять формат MQTT‑топиков.

---

# 4. MQTT Router

MQTT Router — центральный обработчик всех MQTT сообщений:

```
telemetry → telemetry_handler
status → status_handler
command_response → command_handler
ota/status → ota_handler
```

Router обязан:

- валидировать payload,
- преобразовывать строки в числа,
- передавать данные в pipeline (DB + controllers),
- не допускать блокировок.

---

# 5. Command Dispatcher

Command Dispatcher отвечает за отправку команд узлам:

```python
async def run_command_dispatcher():
 while True:
 cmds = db.get_queued_commands(limit=10)
 for cmd in cmds:
 topic = f"hydro/{gh}/{zone}/{node}/{channel}/command"
 await mqtt.publish(topic, json.dumps(cmd_payload))
 db.mark_sent(cmd)
 await asyncio.sleep(dispatcher_interval)
```

### Требования:

- QoS=1 (если доступно),
- Повторы команд запрещены,
- Если 3 попытки публикации подряд — ERROR.

ИИ может:
- улучшить retry/backoff,
- добавить логирование.

ИИ не может:
- изменять формат команды.

---

# 6. Zone Controller Runner

Ниже — главный цикл контроллеров:

```python
async def run_zone_controllers():
 while True:
 zones = db.get_active_zones()
 for zone in zones:
 run_ph(zone)
 run_ec(zone)
 run_climate(zone)
 run_irrigation(zone)
 run_lighting(zone)
 await asyncio.sleep(controller_interval)
```

### Требования:
- Контроллеры всегда выполняются последовательно для каждой зоны.
- Контроллеры не должны выполнять I/O (всё через DB + add_command).
- Контроллеры должны быть **детерминированными**, без рандома.

---

# 7. Жизненный цикл контроллеров (2.0)

Каждый контроллер должен:

1. Прочитать из `telemetry_last`
2. Прочитать цели рецепта (`zone_recipe_instances`)
3. Применить фильтры (SMA)
4. Сравнить с target
5. Проверить cooldown
6. Проверить alerts
7. Сформировать команду или ничего не делать
8. Записать результат логически (events)

ИИ‑агент не может нарушать этот цикл.

---

# 8. Housekeeping Engine

Запускается каждые 60 сек:

- помечает узлы OFFLINE, если last_seen_at > 90 сек;
- проверяет зоны:
 - если в зоне нет telemetry больше 3 минут → ставит статус WARNING;
- архивирует устаревшие события;
- определяет отклонения трендов (опциональная аналитика).

ИИ может расширять housekeeping.

---

# 9. Обработка ошибок

Scheduler должен быть невалипируемым:

- каждая задача завернута в:

```python
try:
 await run_all_scheduled_jobs_once()
except Exception as e:
 log.error(e)
```

- падение одной задачи → не должно останавливать loop;
- MQTT reconnect должен быть автоматический.

---

# 10. Параллельность и тайминг

### Главный цикл:

```
mqtt_listener → realtime 
controller_runner → каждые 5–10 сек 
command_dispatcher → каждые 1 сек 
housekeeping → каждые 60 сек
```

### Ограничения:

- controller_runner не должен выполняться дольше 5 сек;
- никакой блокировки DB более 50–100ms;
- никаких `sleep` внутри контроллеров.

---

# 11. Правила для ИИ

ИИ может:

- добавлять новые контроллеры,
- улучшать алгоритмы,
- добавлять фильтры,
- расширять housekeeping,
- улучшать систему команд (логирование, retry).

ИИ не может:

- менять структуру MQTT payload,
- менять структуру команд,
- менять порядок pipeline,
- создавать команды напрямую минуя dispatcher.

---

# 12. Чек‑лист ИИ перед изменением Scheduler

1. Контроллеры не нарушают порядковый цикл? 
2. Нет ли блокирующего I/O в контроллерах? 
3. MQTT listener не перегружен? 
4. Команд слишком много? (≤ 10 за цикл) 
5. Обновление telemetry_last корректно? 
6. DB транзакции работают быстрее 100ms? 
7. Controller_interval не < 3 сек? 
8. Housekeeping не делает тяжёлых запросов? 

---

# 13. Расширения для будущих версий (2.0)

ИИ может предложить в будущем:

- параллельные контроллеры по зонам,
- планировщик на cron‑базе,
- ML‑анализ трендов pH/EC,
- предсказание объёма дозирования,
- адаптивные интервалы irrigation.

---

# Конец файла SCHEDULER_ENGINE.md
