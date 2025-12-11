# COMMAND_VALIDATION_ENGINE.md
# Полная система проверки команд в 2.0
# HMAC • Timestamp • Limits • Safety • Restrictions • Node-level Validation

Документ описывает полную архитектуру проверки команд (Command Validation)
в системе 2.0. Это критический слой безопасности между Python → ESP32 узлами.

---

# 1. Основная концепция

Любая команда, отправляемая узлу ESP32, должна пройти три уровня валидации:

```
Laravel → Python Scheduler → ESP32 Firmware
```

Каждый уровень выполняет свои проверки.

---

# 2. Формат команды

Команда, отправляемая в MQTT:

```json
{
 "cmd": "dose",
 "params": { "ml": 1.2 },
 "cmd_id": "cmd-abc123",
 "ts": 1737355112,
 "sig": "a1b2c3d4e5f6..."
}
```

Обязательные поля:

| Поле | Описание |
|------|----------|
| cmd | действие (string) |
| params | аргументы команды (object, опционально) |
| cmd_id | уникальный ID (string) |
| ts | Unix timestamp в секундах (number, int64) |
| sig | HMAC-SHA256 подпись в hex формате, 64 символа (string) |

**Примечание:** Поля `ts` и `sig` опциональны для обратной совместимости. Если они отсутствуют, команда обрабатывается с предупреждением в логах.

---

# 3. Уровень 1 — Laravel Validation

Laravel проверяет:

1. **Права пользователя** 
2. **role permissions** 
3. **zone_id / node_id корректны** 
4. **channel принадлежит node** 
5. **проверка allowed commands** 
6. **params валидны** 
7. **нет активных блокировок safety (например, low water)** 

Laravel НЕ отправляет команду напрямую в MQTT. 
Laravel создаёт запись в таблице `commands`.

---

# 4. Уровень 2 — Python Scheduler Validation

Python Dispatcher выполняет:

## 4.1. Проверка срока годности команды

```
abs(now - ts) < 10 секунд
```

## 4.2. Проверка стилей параметров

Пример:

### Команда DOSE:
```
0.1 ≤ ml ≤ 5.0
```

### Команда RUN_PUMP:
```
1 ≤ sec ≤ 60
```

### Команда LIGHT_ON:
```
"cmd": "on"
```

### Valve:
```
"select_line": integer 1..4
```

## 4.3. Проверка состояния зоны

Примеры блокировок:

- `WATER_LEVEL_LOW` → запрещает полив/дозирование
- `NO_FLOW` → запрещает запуск насоса
- `TEMP_HIGH` → блокирует обогреватель
- `EC controller busy` → запрещает вторую дозу

## 4.4. Проверка частоты команд

```
не более 1 дозы pH за 20 сек
не более 1 EC-дозы за 10 сек
не более 1 запуска полива за interval_sec
```

## 4.5. HMAC Sign

Python вычисляет подпись:

```
sig = HMAC_SHA256(node_secret, cmd + '|' + ts)
```

И добавляет ее в MQTT payload.

---

# 5. Уровень 3 — ESP32 Firmware Validation

Прошивка проверяет:

## 5.1. Timestamp

```
abs(now - ts) < 10 секунд
```

Где `now` и `ts` — Unix timestamp в секундах.

## 5.2. HMAC-подпись

```
sig == HMAC_SHA256(node_secret, cmd + '|' + ts)
```

Где:
- `node_secret` — секретный ключ из NodeConfig (поле `node_secret`) или дефолтный
- `cmd` — имя команды (строка)
- `ts` — timestamp в секундах
- Разделитель: `|`
- Подпись в hex формате (64 символа, нижний регистр)
- Сравнение регистронезависимое

## 5.3. Параметры

Проверка диапазонов:

| Команда | Диапазон |
|---------|----------|
| dose | 0.1–5.0 ml |
| run pump | 1–60 sec |
| valve select | допустимые линии |
| heater | only on/off |

## 5.4. Защита двигателя

Если команда пытается запустить насос дольше max_time:

```
stop after auto_cutoff
emit error
```

## 5.5. Защита от конфликтов

Например:

- нельзя выполнить `run` пока насос уже работает 
- нельзя выполнять две команды одновременно на один pump 

## 5.6. Watchdog Recovery

Если команда зависла:

- задача перезагружается 
- команда помечается как error 

---

# 6. Командные статусы

ESP32 отвечает:

```json
{
 "cmd_id": "abc",
 "status": "ok",
 "details": {"duration": 8},
 "ts": 123456
}
```

Или:

```
"status": "error"
"error": "low water"
```

Laravel обновляет таблицу:

```
status = sent / ack / error / timeout
```

---

# 7. Таблица ограничений безопасности

| Узел | Команда | Ограничение |
|------|----------|--------------|
| pH-pump | dose | min interval = 20 sec |
| EC-pump | dose | min interval = 10 sec |
| irrigation | run | only if water_level ≥ 0.2 |
| irrigation | run | max 3600 ml/day |
| valve | select | only idle |
| heater | on | temp < target |
| cooler | on | temp > target |

---

# 8. Анти-спам защита

Python отслеживает:

```
max 10 команд в минуту на node
max 3 команды в 10 сек
```

Если превышено:

```
create event: COMMAND_SPAM_PROTECTION
```

---

# 9. Командная очередь

Python создаёт очередь:

```
pending → sending → waiting_response → done
```

Dispatcher:

1. отсылает 1 команду
2. ждёт ответ
3. по тайм-ауту → retry (до 3 раз)
4. если нет ответа → error

---

# 10. Автоматический rollback

Если команда вызывает ошибку:

- pH дозировка отменяется
- насос останавливается
- valve сбрасывается в idle
- создаётся alert

---

# 11. Логирование

Каждая команда логируется в events:

```
COMMAND_SENT
COMMAND_ACK
COMMAND_RETRY
COMMAND_TIMEOUT
COMMAND_ERROR
```

---

# 12. Правила для ИИ

ИИ может:

- ужесточить проверки,
- добавить новые командные лимиты,
- улучшить алгоритм retry,
- добавить контекстные проверки (например temp+humidity).

ИИ НЕ может:

- отключить HMAC,
- ослабить timestamp,
- убрать проверки безопасности,
- убрать ограничение частоты команд.

---

# 13. Чек‑лист перед релизом

1. Timestamp проверяется на всех уровнях? 
2. HMAC корректен? 
3. Ограничения команд соблюдаются? 
4. Защита dry-run работает? 
5. Нет двойных команд? 
6. ESP32 валидирует payload? 
7. Python валидирует params? 
8. Laravel валидирует доступ? 
9. Retry работает? 
10. Все статусы команд отображаются в UI? 

---

# Конец файла COMMAND_VALIDATION_ENGINE.md
