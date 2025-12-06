# Production Environment Setup

## Быстрый старт

### 1. Установка переменных окружения

Выполните PowerShell скрипт для установки всех необходимых переменных окружения:

```powershell
cd backend
.\setup-prod-env.ps1
```

Или установите переменные вручную:

```powershell
$env:POSTGRES_PASSWORD="hydro_prod_secure_password_2024"
$env:REVERB_APP_KEY="production_reverb_app_key_2024"
$env:REVERB_APP_SECRET="production_reverb_app_secret_2024_secure"
$env:GRAFANA_ADMIN_PASSWORD="admin_prod_secure_2024"
$env:MQTT_MQTT_BRIDGE_PASS="mqtt_bridge_prod_password_2024"
$env:MQTT_AUTOMATION_ENGINE_PASS="automation_engine_prod_password_2024"
$env:MQTT_HISTORY_LOGGER_PASS="history_logger_prod_password_2024"
$env:MQTT_SCHEDULER_PASS="scheduler_prod_password_2024"
```

### 2. Генерация Laravel API токена (опционально)

Для работы Python сервисов с Laravel API необходимо сгенерировать токен:

```powershell
docker-compose -f docker-compose.prod.yml exec laravel php artisan token:generate
```

Затем установите полученный токен:

```powershell
$env:LARAVEL_API_TOKEN="полученный_токен"
```

### 3. Проверка конфигурации

Убедитесь, что конфигурация валидна:

```powershell
docker-compose -f docker-compose.prod.yml config
```

### 4. Запуск production окружения

```powershell
docker-compose -f docker-compose.prod.yml up -d
```

### 5. Проверка статуса сервисов

```powershell
docker-compose -f docker-compose.prod.yml ps
```

## Переменные окружения

### Обязательные переменные

| Переменная | Описание | Значение по умолчанию |
|------------|----------|----------------------|
| `POSTGRES_PASSWORD` | Пароль для PostgreSQL | *(обязательно)* |
| `REVERB_APP_KEY` | Ключ приложения для Laravel Reverb | *(обязательно)* |
| `REVERB_APP_SECRET` | Секретный ключ для Laravel Reverb | *(обязательно)* |
| `GRAFANA_ADMIN_PASSWORD` | Пароль администратора Grafana | *(обязательно)* |
| `MQTT_MQTT_BRIDGE_PASS` | Пароль MQTT для mqtt-bridge | *(обязательно)* |
| `MQTT_AUTOMATION_ENGINE_PASS` | Пароль MQTT для automation-engine | *(обязательно)* |
| `MQTT_HISTORY_LOGGER_PASS` | Пароль MQTT для history-logger | *(обязательно)* |
| `MQTT_SCHEDULER_PASS` | Пароль MQTT для scheduler | *(обязательно)* |

### Опциональные переменные

| Переменная | Описание | Значение по умолчанию |
|------------|----------|----------------------|
| `POSTGRES_USER` | Пользователь PostgreSQL | `hydro` |
| `POSTGRES_DB` | База данных PostgreSQL | `hydro` |
| `REVERB_APP_ID` | ID приложения Reverb | `app` |
| `REVERB_AUTO_START` | Автоматический запуск Reverb | `true` |
| `REVERB_HOST` | Хост для Reverb | `0.0.0.0` |
| `GRAFANA_ADMIN_USER` | Пользователь администратора Grafana | `admin` |
| `LARAVEL_API_TOKEN` | API токен для Python сервисов | *(пусто)* |

## Безопасность

**ВАЖНО:** Значения в `setup-prod-env.ps1` предназначены для тестирования!

Для реального production окружения:

1. Замените все пароли на безопасные уникальные значения
2. Используйте менеджер секретов (например, Docker Secrets, HashiCorp Vault)
3. Храните секреты вне системы контроля версий
4. Регулярно обновляйте пароли и токены

## Устранение неполадок

### Проблема: "required variable X is missing a value"

**Решение:** Убедитесь, что все обязательные переменные окружения установлены:

```powershell
.\setup-prod-env.ps1
```

### Проблема: Сервисы не запускаются

**Решение:** Проверьте логи:

```powershell
docker-compose -f docker-compose.prod.yml logs [service-name]
```

### Проблема: Laravel API возвращает 401/403

**Решение:** Убедитесь, что `LARAVEL_API_TOKEN` установлен и валиден:

```powershell
docker-compose -f docker-compose.prod.yml exec laravel php artisan token:generate
$env:LARAVEL_API_TOKEN="полученный_токен"
docker-compose -f docker-compose.prod.yml restart automation-engine history-logger
```

## Дополнительная информация

- [Docker Compose документация](https://docs.docker.com/compose/)
- [Laravel Reverb документация](https://laravel.com/docs/reverb)
- [Grafana документация](https://grafana.com/docs/)




