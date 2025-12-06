# Автоматическая настройка Docker при развертывании

## Обзор

При запуске Docker контейнеров все необходимые команды настройки выполняются автоматически. Вам больше не нужно вручную запускать `composer install`, `php artisan migrate` и другие команды.

## Что происходит автоматически

### 1. При сборке образа (Dockerfile)

**Файл:** `backend/laravel/Dockerfile`

- ✅ Установка системных зависимостей (Node.js, Chromium, и др.)
- ✅ Установка Composer зависимостей
  - **Dev окружение** (`docker-compose.dev.yml`): устанавливаются ВСЕ зависимости (включая dev)
  - **Production** (`docker-compose.prod.yml`): только production зависимости
- ✅ Установка npm зависимостей
- ✅ Сборка фронтенда (`npm run build`) для production

### 2. При запуске контейнера (docker-entrypoint.sh)

**Файл:** `backend/laravel/docker-entrypoint.sh`

Каждый раз при старте контейнера автоматически выполняются:

#### Базовая настройка Laravel
- ✅ Создание `.env` файла из `.env.example` (если `.env` не существует)
- ✅ Генерация `APP_KEY` (`php artisan key:generate`)
- ✅ Настройка переменных окружения для Vite

#### Настройка базы данных (только в dev режиме)
- ✅ Ожидание подключения к PostgreSQL (до 30 попыток)
- ✅ Запуск миграций (`php artisan migrate --force`)
- ✅ Запуск сидеров (`php artisan db:seed --force`) - только если БД пустая
  - `AdminUserSeeder` - создание администратора
  - `PresetSeeder` - загрузка пресетов
  - `PlantTaxonomySeeder` - загрузка таксономии растений
  - `FullServiceTestSeeder` - тестовые данные для разработки

#### Оптимизация окружения
- **Dev режим** (`APP_ENV=local`):
  - Отключение opcache для горячей перезагрузки
  - Запуск Vite dev server через Supervisor
  - Создание файла `public/hot` для проксирования Vite
  
- **Production режим**:
  - Включение opcache
  - Кэширование конфигурации (`php artisan config:cache`)
  - Кэширование views (`php artisan view:cache`)
  - Кэширование events (`php artisan event:cache`)

## Команды для работы с Docker

### Первый запуск (с нуля)

```bash
cd /home/georgiy/esp/hydro/hydro2.0/backend

# Запуск в dev режиме
docker compose -f docker-compose.dev.yml up -d --build

# Запуск в production режиме
docker compose -f docker-compose.prod.yml up -d --build
```

### Обновление после изменений в коде

```bash
# Пересборка только Laravel контейнера
docker compose -f docker-compose.dev.yml up -d --build laravel

# Пересборка всех контейнеров
docker compose -f docker-compose.dev.yml up -d --build
```

### Перезапуск без пересборки

```bash
# Перезапуск всех сервисов
docker compose -f docker-compose.dev.yml restart

# Перезапуск только Laravel
docker compose -f docker-compose.dev.yml restart laravel
```

### Остановка сервисов

```bash
# Остановка с сохранением данных
docker compose -f docker-compose.dev.yml down

# Остановка с удалением volumes (удаляет БД!)
docker compose -f docker-compose.dev.yml down -v
```

### Просмотр логов

```bash
# Логи всех сервисов
docker compose -f docker-compose.dev.yml logs -f

# Логи только Laravel
docker compose -f docker-compose.dev.yml logs -f laravel

# Последние 100 строк
docker compose -f docker-compose.dev.yml logs --tail=100 laravel
```

### Выполнение команд внутри контейнера

```bash
# Запуск bash в контейнере
docker compose -f docker-compose.dev.yml exec laravel bash

# Выполнение artisan команд
docker compose -f docker-compose.dev.yml exec laravel php artisan route:list
docker compose -f docker-compose.dev.yml exec laravel php artisan tinker

# Установка дополнительных пакетов
docker compose -f docker-compose.dev.yml exec laravel composer require vendor/package
docker compose -f docker-compose.dev.yml exec laravel npm install package-name
```

## Структура конфигурации

```
backend/
├── docker-compose.dev.yml          # Dev окружение
├── docker-compose.prod.yml         # Production окружение
└── laravel/
    ├── Dockerfile                  # Сборка образа
    ├── docker-entrypoint.sh        # Инициализация при запуске
    ├── supervisord.conf            # Supervisor конфигурация
    ├── reverb-supervisor.conf      # WebSocket сервер
    └── vite-supervisor.conf        # Vite dev server (только dev)
```

## Переменные окружения

### Dev режим
Определяются в `docker-compose.dev.yml`:
- `APP_ENV=local`
- `APP_DEBUG=1`
- `DB_HOST=db`
- `REDIS_HOST=redis`
- И другие...

### Production режим
Загружаются из файла `.env` или переменных окружения системы.

## Порты и доступ к сервисам

| Сервис | Dev Port | Production Port | URL |
|--------|----------|-----------------|-----|
| Laravel API | 8080 | 80 | http://localhost:8080 |
| Grafana | 3000 | 3000 | http://localhost:3000 |
| Prometheus | 9090 | 9090 | http://localhost:9090 |
| PostgreSQL | 5432 | 5432 | localhost:5432 |
| Redis | 6379 | 6379 | localhost:6379 |
| MQTT | 1883 | 1883 | localhost:1883 |
| WebSocket (Reverb) | 6001 | 6001 | ws://localhost:6001 |
| Vite Dev Server | 5173 | - | http://localhost:5173 |

## Учётные записи по умолчанию

После первого запуска автоматически создаются три пользователя с разными ролями:

### 👤 Администратор (полный доступ)
- **Email:** `admin@example.com`
- **Пароль:** `password`
- **Роль:** `admin`

### 👤 Оператор (управление системой)
- **Email:** `operator@example.com`
- **Пароль:** `password`
- **Роль:** `operator`

### 👤 Наблюдатель (только просмотр)
- **Email:** `viewer@example.com`
- **Пароль:** `password`
- **Роль:** `viewer`

> ⚠️ **Важно:** В production окружении обязательно измените пароли!

## Troubleshooting

### Контейнер не запускается

```bash
# Проверка логов
docker compose -f docker-compose.dev.yml logs laravel

# Проверка статуса
docker compose -f docker-compose.dev.yml ps
```

### База данных не подключается

```bash
# Проверка контейнера БД
docker compose -f docker-compose.dev.yml ps db

# Проверка логов БД
docker compose -f docker-compose.dev.yml logs db
```

### Ошибка "vendor не найден"

```bash
# Пересборка с чистого листа
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d --build
```

### Vite не работает

```bash
# Перезапуск контейнера
docker compose -f docker-compose.dev.yml restart laravel

# Проверка логов Vite
docker compose -f docker-compose.dev.yml exec laravel supervisorctl status vite
docker compose -f docker-compose.dev.yml exec laravel supervisorctl tail -f vite
```

## Полезные команды для разработки

```bash
# Очистка кэша Laravel
docker compose -f docker-compose.dev.yml exec laravel php artisan cache:clear
docker compose -f docker-compose.dev.yml exec laravel php artisan config:clear
docker compose -f docker-compose.dev.yml exec laravel php artisan route:clear
docker compose -f docker-compose.dev.yml exec laravel php artisan view:clear

# Создание новой миграции
docker compose -f docker-compose.dev.yml exec laravel php artisan make:migration create_table_name

# Откат последней миграции
docker compose -f docker-compose.dev.yml exec laravel php artisan migrate:rollback

# Пересоздание БД с нуля
docker compose -f docker-compose.dev.yml exec laravel php artisan migrate:fresh --seed
```

## Заключение

Теперь при каждом запуске Docker все команды настройки выполняются автоматически. Вам нужно только запустить `docker compose up -d` и приложение готово к работе!

