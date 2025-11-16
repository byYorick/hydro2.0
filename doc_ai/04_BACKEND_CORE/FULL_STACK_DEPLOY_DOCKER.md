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

Рекомендуемая структура:

```text
hydro2/
 backend-laravel/
 backend-python/
 frontend-laravel/ # фактически это же backend-laravel (Inertia + Vue)
 docker/
 laravel.Dockerfile
 python.Dockerfile
 mosquitto.conf
 docker-compose.yml
 docs/
 TECH_STACK_LARAVEL_INERTIA_VUE3_PG.md
 BACKEND_LARAVEL_PG_AI_GUIDE.md
 PYTHON_MQTT_SERVICE_AI_GUIDE.md
 DATABASE_SCHEMA_AI_GUIDE.md
 MQTT_TOPICS_SPEC_AI_GUIDE.md
 # дополнительные документы по системе 2.0 (можно расширять)
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

- PostgreSQL 16 (или совместимая)
- Одна БД `hydro` для:
 - доменных таблиц (zones, devices, recipes…),
 - телеметрии (telemetry_samples),
 - команд и событий.

### 2.3. Mosquitto

- MQTT брокер (`eclipse-mosquitto`)
- Слушает на порту `1883`.

### 2.4. Python MQTT Service

- Python 3.11+
- Пакеты:
 - `asyncio-mqtt` или `gmqtt`,
 - `sqlalchemy`,
 - `psycopg2` или `asyncpg`,
 - базовые утилиты (pydantic, loguru и т.п. по желанию).

---

## 3. docker-compose.yml (базовый пример)

```yaml
version: "3.9"

services:
 postgres:
 image: postgres:16
 environment:
 POSTGRES_DB: hydro
 POSTGRES_USER: hydro
 POSTGRES_PASSWORD: hydro
 volumes:
 - pgdata:/var/lib/postgresql/data
 ports:
 - "5432:5432"

 mosquitto:
 image: eclipse-mosquitto:2
 volumes:
 - ./docker/mosquitto.conf:/mosquitto/config/mosquitto.conf
 ports:
 - "1883:1883"

 laravel:
 build:
 context: ./backend-laravel
 dockerfile: ../docker/laravel.Dockerfile
 environment:
 APP_ENV: local
 APP_KEY: base64:GENERATE_ME
 DB_CONNECTION: pgsql
 DB_HOST: postgres
 DB_PORT: 5432
 DB_DATABASE: hydro
 DB_USERNAME: hydro
 DB_PASSWORD: hydro
 depends_on:
 - postgres
 ports:
 - "8000:8000"
 volumes:
 - ./backend-laravel:/var/www/html

 python_service:
 build:
 context: ./backend-python
 dockerfile: ../docker/python.Dockerfile
 environment:
 DB_HOST: postgres
 DB_PORT: 5432
 DB_NAME: hydro
 DB_USER: hydro
 DB_PASS: hydro
 MQTT_HOST: mosquitto
 MQTT_PORT: 1883
 depends_on:
 - postgres
 - mosquitto

volumes:
 pgdata:
```

ИИ-агент может:
- добавлять сервисы (grafana, redis, websockets),
- но не должен ломать основную связку.

---

## 4. Dockerfile для Laravel

`docker/laravel.Dockerfile` (минимальный вариант):

```dockerfile
FROM php:8.2-fpm

RUN apt-get update && apt-get install -y \
 git unzip libpq-dev libzip-dev \
 && docker-php-ext-install pdo pdo_pgsql

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

WORKDIR /var/www/html

COPY backend-laravel/composer.json backend-laravel/composer.lock ./
RUN composer install --no-interaction --no-scripts --no-autoloader

COPY backend-laravel/ ./
RUN composer dump-autoload --optimize

CMD php artisan migrate --force && php artisan serve --host=0.0.0.0 --port=8000
```

ИИ-агент не должен:
- удалять миграции из команды запуска,
- менять порт без обновления docker-compose.

---

## 5. Dockerfile для Python-сервиса

`docker/python.Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY backend-python/ ./

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main_mqtt.py"]
```

При необходимости можно добавить второй контейнер:

- `python_scheduler` с `CMD ["python", "main_scheduler.py"]`.

---

## 6. Конфиг Mosquitto

`docker/mosquitto.conf` (минимальный):

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

```env
APP_ENV=local
APP_KEY=base64:GENERATE_ME
APP_DEBUG=true

DB_CONNECTION=pgsql
DB_HOST=postgres
DB_PORT=5432
DB_DATABASE=hydro
DB_USERNAME=hydro
DB_PASSWORD=hydro
```

### 7.2. Python

```env
DB_HOST=postgres
DB_PORT=5432
DB_NAME=hydro
DB_USER=hydro
DB_PASS=hydro
MQTT_HOST=mosquitto
MQTT_PORT=1883
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

- Laravel (Inertia UI): 
 `http://localhost:8000`
- MQTT брокер: 
 `mqtt://localhost:1883`
- PostgreSQL: 
 `localhost:5432`, БД `hydro`

---

## 10. Расширения стека (о чём можно просить ИИ)

ИИ-агент может предложить добавить:

1. **Grafana**:
 - отдельный сервис `grafana` в docker-compose;
 - datasource = PostgreSQL.

2. **Redis**:
 - для очередей Laravel;
 - для кэша.

3. **Laravel WebSockets**:
 - отдельный сервис websockets;
 - использовать для realtime обновлений UI.

4. **Отдельный контейнер python_scheduler**:
 - для контроллеров (main_scheduler.py) отдельно от main_mqtt.py.

---

## 11. Чего нельзя делать ИИ-агенту

- Менять имена сервисов (`postgres`, `mosquitto`, `laravel`, `python_service`) без обновления всех зависимостей.
- Менять порты без синхронизации с конфигами ESP32/клиентов.
- Удалять автоматический запуск миграций без замены на понятный альтернативный процесс.
- Хардкодить IP-адреса внутри контейнеров (использовать имена сервисов).

---

## 12. Чек-лист перед изменением Docker-конфигов

1. Laravel, Python и ESP32 всё ещё могут достучаться до PostgreSQL и MQTT?
2. Имена сервисов не изменены или везде обновлены?
3. Порты на хосте не конфликтуют между собой?
4. Секреты (пароли) не захардкожены в изображениях?
5. В случае добавления новых сервисов (Grafana, Redis) — они не ломают зависимости?

---

# Конец файла FULL_STACK_DEPLOY_DOCKER.md