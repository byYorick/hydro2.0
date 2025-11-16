# FULL_SYSTEM_SECURITY.md
# Полная система безопасности 2.0
# Auth • Network Security • Command Safety • Data Protection • AI Restrictions • Infrastructure Hardening

Документ описывает полную архитектуру безопасности системы 2.0:
Laravel + Python Scheduler + ESP32 Узлы + MQTT + Postgres + UI + AI.

---

# 1. Цели архитектуры безопасности

Система безопасности обеспечивает:

- защиту оборудования,
- защиту данных и команд,
- контроль доступа пользователей,
- защиту сети,
- защиту AI от опасных действий,
- отказоустойчивость и мониторинг,
- безопасное взаимодействие узлов и бэкенда.

---

# 2. Уровни безопасности

Архитектура использует многоуровневую модель:

```
L0 — Hardware Safety (ESP32)
L1 — Command Safety (ESP32)
L2 — Transport Security (MQTT + TLS/TCP)
L3 — Backend Security (Laravel)
L4 — Data Security (Postgres)
L5 — AI Safety Layer
L6 — Infrastructure Security (Docker, server)
L7 — Monitoring & Intrusion Detection
```

---

# 3. Hardware Safety (ESP32)

### 3.1. Electrical Safety
- защита от перегрузок,
- защита насосов (max runtime),
- защита клапанов (stuck detection),
- защита от dry-run,
- защита от перегрева ESP32.

### 3.2. Safe Mode
ESP32 переходит в safe-mode при:

- потере Wi‑Fi > 5 мин,
- критической памяти,
- сбоях сенсоров,
- повторных ошибках команды.

В safe-mode:
- дозирование *запрещено*,
- полив *запрещён*,
- нагреватель/охлаждение *выключается*,
- отправляется статус об ошибке.

---

# 4. Command Safety (ESP32)

Каждая команда проверяется:

- HMAC подпись (SHA256)
- timestamp check (±10 сек)
- диапазон параметров
- состояние оборудования
- block-limits (cooldowns)
- safety triggers (low water, high temp)

Команда отклоняется, если:

- подпись неверна,
- просрочена,
- параметры вне диапазона,
- есть активная тревога зоны.

---

# 5. Transport Security (MQTT)

### 5.1. Уровни защиты MQTT
- User/Password Auth
- ACL (node‑scoped)
- QoS1 guaranteed delivery
- TLS (опционально)
- rate limiting

### 5.2. Пространство имен
Узел имеет право только на:

```
nodes/<node_id>/telemetry
nodes/<node_id>/status
nodes/<node_id>/response
```

Узел НЕ имеет права на:

- командные топики других узлов,
- системные топики,
- административные топики.

---

# 6. Backend Security (Laravel 2.0)

### 6.1. Авторизация
Используется:

- Sanctum Tokens,
- User Roles,
- Permissions,
- Policy Layer.

Роли:

- admin
- operator
- viewer
- automation_bot

### 6.2. Ограничения ролей

| Роль | Полив | Дозирование | Рецепты | Настройки | Узлы | AI |
|------|-------|-------------|---------|-----------|------|----|
| admin | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| operator | ✓ | ✓ | ✓ | ограничено | ограничено | частично |
| viewer | ✗ | ✗ | ✗ | ✗ | чтение | ✗ |
| bot | ✓ | ограничено | ✗ | ✗ | ✗ | ✓ |

### 6.3. API‑фильтры

Все API проходят:

- Auth middleware
- Rate limiting
- Permissions
- Safety validation
- Command pre-check

---

# 7. Data Security (Postgres)

### 7.1. Шифрование
- шифрование резервных копий,
- шифрование на уровне диска (LUKS/ZFS encryption),
- защита connection string.

### 7.2. Политики таблиц
- RLS (Row-Level Security) опционально,
- ограничение прав пользователям,
- отдельный пользователь DB для Laravel.

### 7.3. Проверки целостности
- constraint validation,
- логирование всех изменений.

---

# 8. AI Safety Layer

Искусственный интеллект ограничен:

ИИ может:
- рекомендовать параметры,
- корректировать small-range targets,
- запускать симуляции,
- создавать рецепты,
- анализировать ошибки.

ИИ НЕ может:
- отправлять команды напрямую железу,
- отключать safety,
- превышать пороги рецептов (>15%),
- запускать аварийные действия,
- изменять hardware profile,
- изменять права пользователей.

### 8.1. AI Command Sandbox

Перед командой:

```
AI → Simulation Engine → Safety Validator → Command Engine
```

---

# 9. Infrastructure Security (Docker + Server)

### 9.1. Docker Isolation
- каждый сервис в отдельном контейнере,
- минимизированы права,
- no-root policy,
- read-only volume для конфигов.

### 9.2. Firewall
Разрешены только:

- 80/443 (UI/API),
- 1883 (MQTT),
- 5432 (Postgres — локально),
- SSH (порт меняется).

### 9.3. Fail2Ban
Останов атак на:
- SSH
- API brute force
- invalid token attempts

### 9.4. Certificates
Авто‑обновление SSL (Let's Encrypt).

---

# 10. Monitoring & Intrusion Detection

Мониторинг:

- health nodes,
- health zones,
- CPU/RAM/Disk,
- command latency,
- failed command attempts,
- suspicious patterns.

Аномалии:

- резкие pH/EC скачки,
- необычные пакеты MQTT,
- необычное поведение узлов,
- подозрительные API запросы,
- необычные токены.

---

# 11. Disaster Recovery

Система умеет:

- автоматические бэкапы,
- восстановление узлов,
- fallback режим (minimal operations),
- прием телеметрии при частичном падении сервисов,
- локальная буферизация данных на узлах.

---

# 12. Чек‑лист безопасности перед релизом

1. Работает безопасное дозирование? 
2. pH/EC/климат контроллеры не обходят safety? 
3. MQTT ACL правильно настроены? 
4. TLS включён? (опционально) 
5. Роли и permissions работают? 
6. AI ограничен? 
7. Firewall настроен? 
8. Бэкапы создаются? 
9. Monitoring активен? 
10. Узлы уходят в safe mode при ошибках? 

---

# Конец файла FULL_SYSTEM_SECURITY.md
