# Production Environment Setup

Развёртывание через `backend/docker-compose.prod.yml` на Linux/macOS.

## Быстрый старт

### 1. Сгенерировать секреты и env-файл

```bash
# из корня репозитория
make prod-setup PROD_SETUP_ARGS="--host your-server.example.com"
```

Скрипт создаёт:

- `backend/.env.prod` — пароли, токены, `APP_KEY`, домены
- `backend/services/mqtt-bridge/passwords.txt` — MQTT-пользователи для Mosquitto

Перезапись существующего файла:

```bash
make prod-setup PROD_SETUP_ARGS="--force --host 192.168.1.50"
```

Шаблон для ручного редактирования: `backend/.env.prod.example`.

### 2. Проверить конфигурацию

```bash
make prod-check
```

### 3. Запустить стек

```bash
make prod-up
```

Первый запуск после поднятия БД:

```bash
make prod-migrate
make prod-seed    # StartUsersSeeder — базовые пользователи
```

### 4. Статус и логи

```bash
make prod-ps
make prod-logs SERVICE=laravel
```

Остановка:

```bash
make prod-down
```

## Обязательные переменные (`backend/.env.prod`)

| Переменная | Описание |
|------------|----------|
| `PUBLIC_HOST` | Домен или IP сервера (без схемы) |
| `APP_URL` | Полный URL веб-приложения |
| `APP_KEY` | Laravel application key (`base64:...`) |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL |
| `REVERB_APP_KEY` / `REVERB_APP_SECRET` | Laravel Reverb |
| `REVERB_ALLOWED_ORIGINS` | Origins для WebSocket (через запятую) |
| `SANCTUM_STATEFUL_DOMAINS` | Домены для cookie-auth |
| `PY_API_TOKEN` / `PY_INGEST_TOKEN` | Токены Laravel ↔ Python |
| `LARAVEL_API_TOKEN` | Токен Python → Laravel API |
| `MQTT_*_PASS` | Пароли MQTT для сервисов и `MQTT_ESP32_NODE_PASS` для узлов |
| `GRAFANA_ADMIN_PASSWORD` | Пароль Grafana |

Опционально: `PUBLIC_SCHEME` (`https`), `PUBLIC_WS_PORT`, `PUBLIC_WS_TLS`, `SESSION_DOMAIN`.

## ESP32 / MQTT

- Брокер: порт **1883** (в production включена аутентификация)
- Пользователь узлов: `esp32_node`
- Пароль: значение `MQTT_ESP32_NODE_PASS` из `backend/.env.prod`
- На роутере/firewall откройте 1883 только для локальной сети теплицы

## Безопасность

1. **Не коммитьте** `backend/.env.prod` и `passwords.txt`
2. Замените тестовые значения на уникальные перед боевым деплоем
3. Для внешнего доступа используйте reverse proxy (nginx/Caddy) с TLS; `PUBLIC_SCHEME=https`
4. Закройте порты Grafana/Prometheus/Alertmanager файрволом или VPN
5. Регулярно ротируйте пароли и API-токены

После деплоя в контейнере Laravel:

```bash
make prod-check   # env + compose
docker compose --env-file backend/.env.prod -f backend/docker-compose.prod.yml exec laravel php artisan security:check-config
```

## Устранение неполадок

### `required variable X is missing a value`

Запустите `make prod-setup` или заполните переменную в `backend/.env.prod`, затем `make prod-check`.

### Laravel API 401/403 из Python-сервисов

Убедитесь, что `LARAVEL_API_TOKEN` в `.env.prod` совпадает с токеном Sanctum. При необходимости сгенерируйте новый:

```bash
docker compose --env-file backend/.env.prod -f backend/docker-compose.prod.yml exec laravel php artisan token:generate
```

Обновите `LARAVEL_API_TOKEN` в `.env.prod` и перезапустите Python-сервисы:

```bash
docker compose --env-file backend/.env.prod -f backend/docker-compose.prod.yml restart mqtt-bridge automation-engine history-logger
```

### Сервисы не стартуют

```bash
make prod-logs SERVICE=laravel
make prod-logs SERVICE=automation-engine
```

## Альтернатива: bare-metal

Развёртывание без Docker: `infra/DEPLOYMENT.md`, скрипт `./deploy.sh production`.

## Ссылки

- [FULL_STACK_DEPLOY_DOCKER.md](../../doc_ai/04_BACKEND_CORE/FULL_STACK_DEPLOY_DOCKER.md)
- [SECURITY_ARCHITECTURE.md](../../doc_ai/08_SECURITY_AND_OPS/SECURITY_ARCHITECTURE.md)
