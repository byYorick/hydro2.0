# FULL_STACK_DEPLOY_DOCKER.md
# Полный гайд по деплою стека 2.0 в Docker
# (Laravel + PostgreSQL + Python MQTT Service + Mosquitto + Inertia/Vue)

Этот документ описывает, **как ИИ-агенты и люди должны разворачивать весь стек 2.0** 
в Docker-среде: от структуры репозитория до docker-compose и переменных окружения.

Цель: получить воспроизводимую среду, где:

- Laravel обслуживает UI и API,
- PostgreSQL хранит доменную модель и телеметрию,
- Mosquitto обслуживает MQTT-трафик узлов ESP32,
- Python-сервис обрабатывает MQTT и управляет контроллерами.

---

## 1. Структура репозитория

Актуальная структура проекта:

```text
hydro2.0/
 backend/
  laravel/              # Laravel приложение (Inertia + Vue 3)
  services/             # Python сервисы
   mqtt-bridge/
   history-logger/
   automation-engine/
   scheduler/
   common/              # Общая библиотека для Python сервисов
  docker-compose.dev.yml
  docker-compose.prod.yml
  configs/              # Конфигурации для dev/prod
 ../                # Документация
 firmware/              # Прошивки ESP32
 mobile/                # Android приложение
 infra/                 # Инфраструктура (Terraform, Ansible, K8s)
```

**Правило для ИИ-агентов:** 
не менять эту структуру кардинально, только дополнять.

---

## 2. Компоненты стека

### 2.1. Laravel (PHP)

- PHP 8.2+
- Laravel 10/11
- Inertia + Vue 3
- Подключение к PostgreSQL

### 2.2. PostgreSQL

- PostgreSQL 16 (или совместимая, TimescaleDB для production)
- База данных:
 - Development: `hydro_dev`
 - Production: `hydro`
- Содержит:
 - доменные таблицы (zones, devices, recipes…),
 - телеметрию (telemetry_samples),
 - команды и события.

### 2.3. Mosquitto

- MQTT брокер (`eclipse-mosquitto`)
- Слушает на порту `1883`.

### 2.4. Python MQTT Services

- Python 3.11+
- Несколько независимых сервисов:
 - `mqtt-bridge` - FastAPI мост для отправки команд через MQTT
 - `history-logger` - запись телеметрии в PostgreSQL
 - `automation-engine` - контроллер зон, проверка targets
 - `scheduler` - расписания поливов/света из recipe phases
- Общая библиотека `common/` для всех сервисов
- Пакеты: `asyncio-mqtt` или `gmqtt`, `sqlalchemy`, `psycopg2` или `asyncpg`, `pydantic`, `loguru`

### 2.5. Redis

- Redis 7+ для кэша и сессий Laravel
- Используется для очередей и realtime обновлений

### 2.6. Laravel Reverb (WebSocket)

- Встроенный WebSocket сервер Laravel
- Используется для realtime обновлений UI
- Порт: `6001`

---

## 3. docker-compose.yml (актуальная структура)

Основные сервисы:

```yaml
version: "3.9"

services:
 db:
   image: timescale/timescaledb:latest-pg16
   environment:
     POSTGRES_DB: hydro_dev  # или hydro для production
     POSTGRES_USER: hydro
     POSTGRES_PASSWORD: hydro
   volumes:
     - postgres_data:/var/lib/postgresql/data
   ports:
     - "5432:5432"

 mqtt:
   image: eclipse-mosquitto:2
   ports:
     - "1883:1883"

 redis:
   image: redis:7-alpine
   ports:
     - "6379:6379"

 laravel:
   build:
     context: ./laravel
     dockerfile: Dockerfile
   environment:
     APP_ENV: local
     DB_HOST: db
     DB_DATABASE: hydro_dev  # или hydro для production
     REDIS_HOST: redis
     REVERB_APP_ID: app
     REVERB_APP_KEY: local
     REVERB_APP_SECRET: secret
   depends_on:
     - db
     - redis
   ports:
     - "8080:80"      # HTTP
     - "5173:5173"    # Vite dev server (только dev)
     - "6001:6001"    # Reverb WebSocket

 mqtt-bridge:
   build:
     context: ./services
     dockerfile: mqtt-bridge/Dockerfile
   environment:
     MQTT_HOST: mqtt
     PG_HOST: db
     PG_DB: hydro_dev  # или hydro для production
     LARAVEL_API_URL: http://laravel
   depends_on:
     - mqtt
     - db
     - laravel
   ports:
     - "9000:9000"

 history-logger:
   build:
     context: ./services
     dockerfile: history-logger/Dockerfile
   environment:
     MQTT_HOST: mqtt
     PG_HOST: db
     PG_DB: hydro_dev  # или hydro для production
   depends_on:
     - mqtt
     - db

 automation-engine:
   build:
     context: ./services
     dockerfile: automation-engine/Dockerfile
   environment:
     MQTT_HOST: mqtt
     PG_HOST: db
     PG_DB: hydro_dev  # или hydro для production
     LARAVEL_API_URL: http://laravel
     LARAVEL_API_TOKEN: ${LARAVEL_API_TOKEN}
   depends_on:
     - mqtt
     - db
     - laravel
   ports:
     - "9401:9401"

 scheduler:
   build:
     context: ./services
     dockerfile: scheduler/Dockerfile
   environment:
     MQTT_HOST: mqtt
     PG_HOST: db
     PG_DB: hydro_dev  # или hydro для production
   depends_on:
     - mqtt
     - db
   ports:
     - "9402:9402"

volumes:
 postgres_data:
```

ИИ-агент может:
- добавлять сервисы (grafana, redis, websockets),
- но не должен ломать основную связку.

---

## 4. Dockerfile для Laravel

`backend/laravel/Dockerfile`:

```dockerfile
FROM php:8.2-fpm

RUN apt-get update && apt-get install -y \
 git unzip libpq-dev libzip-dev \
 && docker-php-ext-install pdo pdo_pgsql

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

WORKDIR /app

COPY composer.json composer.lock ./
RUN composer install --no-interaction --no-scripts --no-autoloader

COPY . ./
RUN composer dump-autoload --optimize

CMD php artisan migrate --force && php artisan serve --host=0.0.0.0 --port=80
```

**Примечание:** В production используется Apache/Nginx через `supervisord`, порт `80` внутри контейнера, внешний порт `8080`.

ИИ-агент не должен:
- удалять миграции из команды запуска,
- менять порт без обновления docker-compose.

---

## 5. Dockerfile для Python-сервисов

Каждый сервис имеет свой Dockerfile в `backend/services/<service-name>/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY common/ ./common/
COPY <service-name>/ ./

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
```

**Сервисы:**
- `mqtt-bridge` - FastAPI сервис на порту `9000`
- `history-logger` - подписка на MQTT, запись телеметрии
- `automation-engine` - контроллер зон, порт `9401` (Prometheus metrics)
- `scheduler` - расписания, порт `9402` (Prometheus metrics)

---

## 6. Конфиг Mosquitto

`backend/services/mqtt-bridge/mosquitto.dev.conf` (для dev):

```conf
listener 1883
allow_anonymous true
```

ИИ-агент может:
- добавить авторизацию,
- включить persistence,
- но не должен менять порт без синхронизации с env.

---

## 7. Переменные окружения (env)

### 7.1. Laravel

`.env` (или environment секция docker-compose):

**Development:**
```env
APP_ENV=local
APP_DEBUG=true
DB_CONNECTION=pgsql
DB_HOST=db
DB_PORT=5432
DB_DATABASE=hydro_dev
DB_USERNAME=hydro
DB_PASSWORD=hydro
REDIS_HOST=redis
REDIS_PORT=6379
BROADCAST_DRIVER=reverb
REVERB_APP_ID=app
REVERB_APP_KEY=local
REVERB_APP_SECRET=secret
REVERB_HOST=0.0.0.0
REVERB_PORT=6001
REVERB_SCHEME=http
REVERB_DEBUG=true
REVERB_AUTO_START=true
```

**Production:**
```env
APP_ENV=production
APP_DEBUG=false
DB_CONNECTION=pgsql
DB_HOST=db
DB_PORT=5432
DB_DATABASE=hydro
DB_USERNAME=hydro
DB_PASSWORD=change-me
REDIS_HOST=redis
REDIS_PORT=6379
BROADCAST_DRIVER=reverb
REVERB_APP_ID=app
REVERB_APP_KEY=change-me
REVERB_APP_SECRET=change-me
REVERB_HOST=0.0.0.0
REVERB_PORT=6001
REVERB_SCHEME=http
REVERB_DEBUG=false
REVERB_AUTO_START=true
```

### 7.2. Python Services

**Общие переменные для всех Python сервисов:**
```env
MQTT_HOST=mqtt
MQTT_PORT=1883
PG_HOST=db
PG_PORT=5432
PG_DB=hydro_dev  # или hydro для production
PG_USER=hydro
PG_PASS=hydro
```

**Для automation-engine и mqtt-bridge (требуют доступ к Laravel API):**
```env
LARAVEL_API_URL=http://laravel
LARAVEL_API_TOKEN=<token>  # Генерируется через Laravel Sanctum или отдельный API token
```

**Генерация токенов:**

1. **LARAVEL_API_TOKEN** - для Python сервисов:
   ```bash
   # В Laravel контейнере
   php artisan tinker
   >>> $token = \App\Models\User::first()->createToken('python-service')->plainTextToken;
   >>> echo $token;
   ```

2. **REVERB_APP_KEY и REVERB_APP_SECRET** - для WebSocket:
   ```bash
   # В Laravel контейнере
   php artisan reverb:install
   # Или сгенерировать вручную через openssl
   ```

3. **PY_API_TOKEN** - для Laravel → Python bridge (опционально):
   ```bash
   # Можно использовать тот же LARAVEL_API_TOKEN или отдельный
   ```

ИИ-агент не должен:
- хардкодить пароли в коде,
- использовать отличающиеся значения для DB в Laravel и Python.

---

## 8. Процесс запуска (end-to-end)

1. Клонировать репозиторий или распаковать.
2. Заполнить `.env` для Laravel (минимум APP_KEY и DB).
3. Собрать и запустить контейнеры:
 ```bash
 docker-compose up --build
 ```
4. Laravel:
 - при старте выполняет `php artisan migrate --force`.
5. Python-сервис:
 - подключается к PostgreSQL и Mosquitto,
 - подписывается на `hydro/#`.
6. ESP32-узлы:
 - настраиваются на подключение к MQTT-брокеру (`host = IP контейнера/хоста`),
 - начинают публиковать telemetry/status.

---

## 9. Локальный доступ

**Development окружение:**
- Laravel (Inertia UI): `http://localhost:8080`
- Vite dev server: `http://localhost:5173` (только dev)
- Reverb WebSocket: `ws://localhost:6001`
- MQTT брокер: `mqtt://localhost:1883`
- PostgreSQL: `localhost:5432`, БД `hydro_dev`
- Redis: `localhost:6379`
- Prometheus: `http://localhost:9090` (если включен)
- Grafana: `http://localhost:3000` (если включен)

**Production окружение:**
- Laravel (Inertia UI): `http://localhost:8080`
- Reverb WebSocket: `ws://localhost:6001`
- MQTT брокер: `mqtt://localhost:1883` (внутренний, не публичный)
- PostgreSQL: `localhost:5432`, БД `hydro` (внутренний)

---

## 10. Расширения стека (о чём можно просить ИИ)

ИИ-агент может предложить добавить:

1. **Grafana**:
 - отдельный сервис `grafana` в docker-compose;
 - datasource = PostgreSQL.

2. **Redis**:
 - для очередей Laravel;
 - для кэша.

3. **Laravel Reverb (WebSocket)**:
 - встроен в Laravel сервис;
 - автоматически запускается при `REVERB_AUTO_START=true`;
 - используется для realtime обновлений UI;
 - см. раздел 13 ниже.

4. **Python сервисы уже разделены**:
 - `scheduler` - отдельный контейнер для расписаний;
 - `automation-engine` - отдельный контейнер для контроллеров зон;
 - `history-logger` - отдельный контейнер для записи телеметрии;
 - `mqtt-bridge` - отдельный контейнер для REST → MQTT моста.

---

## 11. Чего нельзя делать ИИ-агенту

- Менять имена сервисов (`db`, `mqtt`, `laravel`, `redis`, `mqtt-bridge`, `history-logger`, `automation-engine`, `scheduler`) без обновления всех зависимостей.
- Менять порты без синхронизации с конфигами ESP32/клиентов.
- Удалять автоматический запуск миграций без замены на понятный альтернативный процесс.
- Хардкодить IP-адреса внутри контейнеров (использовать имена сервисов).
- Менять структуру `backend/services/` без обновления Dockerfile путей.

---

## 12. Чек-лист перед изменением Docker-конфигов

1. Laravel, Python и ESP32 всё ещё могут достучаться до PostgreSQL и MQTT?
2. Имена сервисов не изменены или везде обновлены?
3. Порты на хосте не конфликтуют между собой?
4. Секреты (пароли, токены) не захардкожены в изображениях?
5. В случае добавления новых сервисов (Grafana, Redis, Prometheus) — они не ломают зависимости?
6. Reverb WebSocket правильно настроен для realtime обновлений?

---

## 13. Laravel Reverb (WebSocket)

Laravel Reverb — встроенный WebSocket сервер для realtime обновлений UI.

### 13.1. Конфигурация

Reverb автоматически запускается при старте Laravel контейнера, если `REVERB_AUTO_START=true`.

**Переменные окружения:**
- `REVERB_APP_ID` - идентификатор приложения (по умолчанию: `app`)
- `REVERB_APP_KEY` - публичный ключ для клиентов
- `REVERB_APP_SECRET` - секретный ключ для сервера
- `REVERB_HOST` - хост для прослушивания (по умолчанию: `0.0.0.0`)
- `REVERB_PORT` - порт WebSocket (по умолчанию: `6001`)
- `REVERB_SCHEME` - схема (`http` или `https`)
- `REVERB_DEBUG` - режим отладки (только для dev)
- `REVERB_AUTO_START` - автоматический запуск при старте контейнера

### 13.2. Подключение клиентов

**Frontend (Vue 3):**
```javascript
import Echo from 'laravel-echo';
import Pusher from 'pusher-js';

window.Pusher = Pusher;
window.Echo = new Echo({
    broadcaster: 'reverb',
    key: import.meta.env.VITE_REVERB_APP_KEY,
    wsHost: import.meta.env.VITE_REVERB_HOST,
    wsPort: import.meta.env.VITE_REVERB_PORT,
    wssPort: import.meta.env.VITE_REVERB_PORT,
    forceTLS: (import.meta.env.VITE_REVERB_SCHEME ?? 'https') === 'https',
    enabledTransports: ['ws', 'wss'],
});
```

### 13.3. Использование

См. `REALTIME_UPDATES_ARCH.md` для детального описания событий и каналов.

**Основные каналы:**
- `hydro.zones.{id}` - обновления по зоне
- `hydro.alerts` - новые алерты
- `nodes.{id}.status` - статусы узлов

### 13.4. Мониторинг

Reverb логирует подключения и события. В production рекомендуется настроить логирование в файл или внешний сервис.

---

# Конец файла FULL_STACK_DEPLOY_DOCKER.md