# GLOBAL_SCHEDULER_ENGINE.md
# Глобальный планировщик задач 2.0 (Global Scheduler Engine)
# Orchestration • Controllers • Timing • Automation • AI Integration • Multi‑Zone Management

Документ описывает полный Global Scheduler Engine — центральный мозг системы 2.0,
который координирует работу зон, контроллеров, симуляций, AI, команд и расписаний.

---

# 1. Назначение Global Scheduler Engine

Scheduler выполняет:

- запуск контроллеров зон (pH/EC/климат/полив/свет/энергия),
- обработку телеметрии,
- автоматическое планирование задач,
- отправку команд узлам,
- запуск AI оптимизаций,
- симуляции,
- архивирование данных,
- проверку алертов и safety,
- распределение нагрузки.

Это **центральная управляющая логика** между Laravel → Python → ESP32.

---

# 2. Архитектура Scheduler 2.0

```
scheduler/
 ├── core/
 │ ├── loop_engine.py
 │ ├── task_manager.py
 │ ├── cron_manager.py
 │ └── safety_guard.py
 ├── controllers/
 │ ├── ph_controller.py
 │ ├── ec_controller.py
 │ ├── climate_controller.py
 │ ├── light_controller.py
 │ ├── irrigation_controller.py
 │ ├── energy_controller.py
 │ └── ai_controller.py
 ├── mqtt/
 │ ├── mqtt_multi_client.py
 │ ├── mqtt_router.py
 │ ├── command_dispatcher.py
 │ └── telemetry_buffer.py
 ├── ai/
 │ ├── twin_bridge.py
 │ ├── ai_optimizer.py
 │ └── anomaly_detector.py
 ├── db/
 │ ├── db_writer.py
 │ ├── data_aggregator.py
 │ └── retention_manager.py
 ├── recovery/
 │ ├── scheduler_watchdog.py
 │ ├── node_failover.py
 │ └── broker_failover.py
 └── api_bridge/
 ├── laravel_sync.py
 ├── recipe_updater.py
 └── ui_state_exporter.py
```

---

# 3. Цикл работы Global Loop

Каждый тик цикла:

```
while True:
 read_telemetry()
 update_zone_state()
 run_controllers()
 enforce_safety()
 send_commands()
 store_data()
 rotate_logs()
 time.sleep(loop_interval)
```

Интервал:

```
100–300 мс
```

---

# 4. Dispatcher Logic

Dispatcher:

- получает команды из Laravel,
- проверяет их через Safety & Validation Layer,
- подписывает HMAC,
- отправляет узлам через MQTT,
- ждёт ответ,
- делает retry при ошибке.

Dispatcher ведет очередь:

```
pending → sending → waiting → ack/error
```

---

# 5. Контроллеры

## 5.1 PH Controller

Использует:

- pH telemetry,
- drift model,
- recipe targets,
- AI correction.

Команды:

- `dose_acid`
- `dose_base`
- mixing cycle (опционально)

## 5.2 EC Controller

Команды:

- `dose_nutrient`
- `mix_water`
- `balance_ec`

## 5.3 Climate Controller

Управляет:

- вентилятором,
- обогревателем,
- охлаждением,
- увлажнителем,
- осушителем.

## 5.4 Light Controller

Управляет:

- фотопериодом,
- интенсивностью,
- плавным включением (soft-start),
- энергосберегающим режимом.

## 5.5 Irrigation Controller

Управляет:

- интервалами,
- длительностью,
- подтверждением протока (flow),
- volumetric dosing,
- emergency stop.

## 5.6 Energy Controller

Оптимизирует:

- нагрузку,
- графики света,
- работу климат‑оборудования.

## 5.7 AI Controller

Управляет:

- AI оптимизациями,
- рекомендациями,
- adaptive targets,
- anomaly detection.

---

# 6. Multi-Zone Coordination

Scheduler обязан:

- синхронизировать все зоны,
- не допускать конфликтов между зонами,
- блокировать действия при зависимостях (например, shared pump),
- учитывать глобальные лимиты энергии,
- оптимизировать запуск поливов между зонами.

---

# 7. Safety Guard Layer

Проверяет:

- NO_FLOW
- LOW_WATER
- OVERHEAT
- NODE_OFFLINE
- SENSOR_FAIL
- PH DRIFT
- EC DRIFT
- TEMPERATURE CRITICAL
- HUM CRITICAL

Если safety активируется → контроллеры отключаются.

---

# 8. Cron Manager (события по расписанию)

Поддерживает:

- ежедневные задачи,
- недельные задачи,
- ежечасные задачи,
- пользовательские расписания.

Примеры:

- auto-mix water в 3 ночи,
- calibration reminder,
- flush cycle,
- backup run,
- simulation run.

---

# 9. AI Integration

Scheduler взаимодействует с AI:

- отправляет текущие данные,
- получает предложения,
- выполняет симуляции Twin,
- принимает корректировки целей.

AI работает только через sandbox.

---

# 10. Failover & Watchdog

### 10.1 Scheduler Watchdog
Если Scheduler завис:

```
restart process
recover task queue
restore mqtt clients
```

### 10.2 Node Failover
При offline узле:

- заморозить контроллеры
- перейти в degraded mode

### 10.3 Broker Failover
Если MQTT down:

- переключить узлы на резервный брокер
- пересоздать подключения

---

# 11. DB Layer

Scheduler пишет:

- telemetry_raw
- telemetry_last
- events
- alerts
- controller_runtime
- node_states

Каждые 60 мин запускается агрегация.

---

# 12. UI Integration

Scheduler генерирует:

- current_state.json
- zones_runtime.json
- alerts.json
- controller_logs.json

Laravel подтягивает эти файлы в UI.

---

# 13. Чек-лист Scheduler 2.0

1. Все контроллеры работают? 
2. Safety Layer активен? 
3. Commands dispatch корректен? 
4. Retry/Timeout работает? 
5. Multi-zone синхронизация корректна? 
6. AI интеграция работает? 
7. MQTT multi-broker активен? 
8. DB записи корректны? 
9. Failover работает? 
10. Cron задачи запускаются? 

---

# Конец файла GLOBAL_SCHEDULER_ENGINE.md
