# SECURITY_ARCHITECTURE.md
# Полная архитектура безопасности системы 2.0
# MQTT • LAN • Laravel API • Python Service • ESP32 • Tokens • Secrets • Docker

Документ описывает комплексную модель безопасности для гидропонной системы 2.0.
Файл предназначен для:
- backend‑разработчиков (Laravel),
- Python‑сервиса,
- архитекторов LAN/IoT,
- разработчиков прошивок ESP32,
- ИИ‑агентов.

Цель — создать защищённую, отказоустойчивую и расширяемую систему.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

# 1. Основные принципы безопасности 2.0

1. **Zero‑Trust внутри LAN** 
 Каждый узел проверяет подлинность команд.

2. **Минимально необходимые права** 
 Узел может выполнять только команды по своему node_id.

3. **Разделение обязанностей** 
 - Python управляет MQTT и командами. 
 - Laravel управляет пользователями и UI. 
 - ESP32 управляет только собственными каналами.

4. **Защита от несанкционированного OTA** 
 Только сервер может инициировать OTA.

5. **Все операции должны быть журналируемыми** 
 События и алерты фиксируются в БД.

---

# 2. Слой безопасности MQTT

## 2.1. Состояние по умолчанию (2.0)
MQTT работает в режиме:
- внутри LAN,
- anonymous-enabled,
- без логина/пароля.

Это допустимо, если:
- Wi‑Fi скрыт,
- включен WPA2/WPA3,
- LAN недоступна извне.

## 2.2. Рекомендуемая конфигурация для “production”

```
listener 1883
allow_anonymous false

password_file /mosquitto/config/passwords
acl_file /mosquitto/config/acl
```

Пользователь:
```
python_service
```

ACL:
```
user python_service
topic readwrite hydro/#

user esp32
topic readwrite hydro/+/+/esp32/#
topic write hydro/+/+/+/status
```

## 2.3. Подпись команд и конфигураций

### 2.3.1. Подпись команд

Каждая команда должна содержать HMAC‑подпись с timestamp:

```json
{
 "cmd": "dose",
 "params": {"ml": 1.0},
 "ts": 1737355500,
 "sig": "hmacsha256(node_secret, canonical_json(command_without_sig))"
}
```

`canonical_json` — каноническая JSON-строка команды без `sig`:
- ключи объектов отсортированы лексикографически,
- порядок массивов сохраняется,
- сериализация без пробелов,
- числа форматируются как в cJSON (int если целое, иначе 15/17 значащих),
- строки JSON-экранируются, UTF-8, слэши не экранируются.

**Канонический tolerance — 10 секунд** (см. `HMAC_TIMESTAMP_TOLERANCE_SEC` в `firmware/nodes/common/components/node_framework/node_command_handler.c` и `_MAX_TIMESTAMP_SKEW_SEC` в `backend/services/history-logger/commands/command_service.py`).

> История: ранние версии этого документа упоминали «не старше 30 секунд». Это устаревший прицел — реальный firmware/HL контракт `±10 сек`. Точка синхронизации с `COMMAND_VALIDATION_ENGINE.md` §4.1 и §5.1.

### 2.3.2. Подпись конфигураций

Каждая конфигурация узла должна содержать HMAC‑подпись с timestamp:

```json
{
 "node_id": "nd-001",
 "version": 3,
 "ts": 1737355500,
 "sig": "hmacsha256(node_secret, node_id|version|ts)"
}
```

**Контракт:** Узлы ESP32 должны проверять подпись и timestamp (не старше 60 секунд).

**Status: planned / not implemented.** В актуальной прошивке HMAC-верификация **config** в `node_config_handler.c` не реализована — handler принимает push-конфиг и обрабатывает payload без проверки `sig`/`ts`. Безопасность config-канала пока обеспечивается косвенно: ACL MQTT-брокера + закрытая внутренняя сеть. Полная HMAC-валидация конфигов запланирована.

---

# 3. Секреты узлов (Node Secrets)

Каждый узел получает уникальный секрет:

```
node_secret = random(32 bytes)
```

Он хранится в:
- таблице `nodes`,
- конфигурации ESP32 (NVS),
- переменных среды Python‑сервиса.

Используется для:
- HMAC подписи команд,
- валидации OTA.

---

# 4. API-безопасность (Laravel)

## 4.1. Аутентификация

Используется **Laravel Sanctum** (session-cookie для SPA + Personal Access Token / Bearer для API). Passport и JWT в проекте не подключены и не поддерживаются.

Middleware aliases:
- `auth.token` — `AuthenticateWithApiToken` (Session + Bearer)
- `auth:sanctum` — стандартный Sanctum guard для API-роутов
- `admin` — `EnsureAdmin`
- `role` — `EnsureUserHasRole` (со списком ролей в route definition)

Подробнее — `AUTH_SYSTEM.md`.

## 4.2. Права пользователей (Roles)

Роли:
- **admin** — доступ ко всему,
- **operator** — управление зонами,
- **viewer** — только просмотр,
- **agronomist** — управление grow-cycle и рецептами,
- **engineer** — инженерные операции и сервисная диагностика.

## 4.3. Ограничения API

Источник: `backend/laravel/routes/api.php`.

- **Стандартные API**: 120 запросов/мин/IP (production); 1000 (testing/e2e); 2000 (local). Переопределяется через `API_THROTTLE` env.
- **System endpoints** (`/api/system/health`, `/api/system/scheduler/metrics`): 300 запросов/мин/IP — выше для polling мониторинга.
- **Auth endpoints** (`/api/auth/login|logout|me`): 10 запросов/мин/IP + 5 неудачных попыток per `email|IP` (защита от брутфорса).
- **Node register** (`/api/nodes/register`): 10 запросов/мин на `node_uid`/`hardware_id` + burst 120/мин/IP bridge.
- **IP whitelist** для регистрации узлов: `services.node_registration.allowed_ips`. **Канонический тип значения — массив CIDR/IP-строк.** Middleware `NodeRegistrationIpWhitelist` ожидает массив; до миграции `2026_05_28_*` (и фиксации `config/services.php` той же датой) значение приходило строкой и whitelist де-факто пропускал любой запрос. После фикса значение приводится к массиву через `explode(',', ...)` + `array_map('trim')` в `services.php`. ENV: `NODE_REGISTRATION_ALLOWED_IPS` (значение через запятую). Default: `10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`.
- Все изменения рецептов/зон логируются в `zone_events`.

## 4.4. Блокировки и дедупликация

### 4.4.1. Pessimistic Locking при публикации конфигураций

При публикации конфигурации узла используется pessimistic locking (SELECT FOR UPDATE) для предотвращения одновременной публикации одной и той же конфигурации.

### 4.4.2. Optimistic Locking при публикации конфигураций

Дополнительно используется optimistic locking через версионирование (updated_at timestamp) для проверки, что узел не был изменен во время публикации.

### 4.4.3. Advisory Lock для дедупликации

Используется PostgreSQL advisory lock для предотвращения одновременной публикации конфигурации одного узла из разных процессов/потоков.

### 4.4.4. Кеш-дедупликация

Дополнительный уровень защиты через кеш: конфигурации с одинаковым хешем не публикуются повторно в течение 60 секунд.

## 4.5. FormRequest и Policy

Все мутирующие операции защищены через:
- **FormRequest** классы для валидации входных данных
- **Policy** классы для проверки прав доступа
- **API Resource** классы для стандартизации ответов

Доступные Policy (`backend/laravel/app/Policies/`):
- `ZonePolicy` — управление зонами (view, update, setLive, manageCycle, ...)
- `DeviceNodePolicy` — управление узлами
- `CommandPolicy` — управление командами
- `GrowCyclePolicy` — управление grow-циклами (advance, pause, harvest, abort)
- `RecipeRevisionPolicy` — управление ревизиями рецептов

Регистрация — `app/Providers/AuthServiceProvider.php`.

---

# 5. Python Service Security

## 5.1. Ограничения

Python‑сервис:
- НЕ может выполнять команды вне MQTT,
- НЕ имеет доступа к UI,
- НЕ меняет рецепты/зоны.

## 5.2. Секреты и переменные среды

В docker:

```
PYTHON_DB_URL=
MQTT_USER=
MQTT_PASS=
NODE_SECRET_PATH=/secrets/nodes.json
```

## 5.3. Валидация команд

Перед отправкой узлу Python должен проверять:

1. channel разрешён? 
2. node принадлежит zone? 
3. команду отправил авторизованный пользователь? 
4. команда подписана? 

---

# 6. ESP32 Security

## 6.1. Защита OTA

Проверяется:
- SHA256,
- версия,
- подпись URL,
- HMAC запроса.

## 6.2. Защита команд

Каждая команда:
- проверяет timestamp (не старше 10 секунд),
- проверяет подпись.

## 6.3. Защита хранения секретов

Секреты хранятся в:
- secure NVS partition,
- не читаются через OTA,
- не выводятся в логи.

---

# 7. Docker Security

## 7.1. Сетевые ограничения

В docker-compose:

```
networks:
 hydro_net:
 driver: bridge
 internal: true
```

Это отключает всю внешнюю доступность.

Для UI — отдельный nginx proxy.

## 7.2. Разделение контейнеров

- MQTT
- Python-сервисы (AE / HL / mqtt-bridge)
- Laravel Backend
- PostgreSQL
- WebSockets (optional)
- Grafana (optional)

Каждый сервис — свой контейнер.

---

# 8. Стратегия резервного копирования

## 8.1. Что нужно бэкапить:

- PostgreSQL (полные и инкрементальные)
- .env Laravel
- .env Python
- MQTT ACL/пароли
- OTA‑файлы

## 8.2. Частота

- полные бэкапы — каждый день,
- инкрементальные — каждые 6 часов.

---

# 9. Политика обновления безопасности

## 9.1. Узлы ESP32

- обязательная проверка sha256,
- обязательная проверка подписи,
- откат при сбое OTA.

## 9.2. Python

- ежемесячные обновления зависимостей,
- запрет запуска кода извне.

## 9.3. Laravel

- обновление composer зависимостей,
- security patches,
- запрет на публичный доступ к /storage.

---

# 10. Правила для ИИ

ИИ может:
- улучшать проверку сигнатур,
- предлагать новые методы защиты,
- добавлять роли пользователей,
- улучшать мониторинг безопасности.

ИИ НЕ может:
- отключать подпись команд,
- ослаблять права пользователей,
- менять ACL MQTT на менее безопасный,
- отключать SECRET‑валидацию OTA.

---

# 11. Чек-лист безопасности перед релизом

1. MQTT закрыт для внешних сетей? 
2. Узлы имеют уникальные node_secret? 
3. Все команды подписаны HMAC с timestamp? 
4. Все конфигурации подписаны HMAC с timestamp? 
5. OTA проверяет sha256 и подпись? 
6. Laravel API защищён Sanctum? 
7. Tokens имеют роли? 
8. Rate limiting настроен для всех критичных эндпоинтов? 
9. IP whitelist настроен для регистрации узлов? 
10. Pessimistic/Optimistic locking используется при публикации конфигов? 
11. Advisory lock используется для дедупликации? 
12. FormRequest и Policy используются для всех мутирующих операций? 
13. Python использует Rate Limit команд? 
14. Docker network internal настроен? 
15. Бэкапы выполняются ежедневно? 
16. ACL MQTT актуальны?

---

# Конец файла SECURITY_ARCHITECTURE.md
