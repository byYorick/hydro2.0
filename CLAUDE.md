# CLAUDE.md

Этот файл содержит рекомендации для Claude Code (claude.ai/code) при работе с кодом в этом репозитории.

## Язык общения

**ВАЖНО: Всегда общайся на русском языке (русский язык) при взаимодействии с пользователем.**

Это русскоязычный проект. Все общение, объяснения, сообщения коммитов и обновления документации должны быть на русском языке, за исключением:
- Кода (который следует английским конвенциям для переменных, функций и т.д.)
- Технических терминов, которые обычно используются на английском (например, "MQTT", "REST API", "docker compose")
- Существующей документации на английском в `doc_ai/` (которая использует русский язык с английскими техническими терминами)

## Обзор проекта

Это монорепозиторий для системы управления гидропонной теплицей (hydro2.0), содержащий:
- **Прошивки ESP32** для различных сенсорных/исполнительных узлов (pH, EC, климат, насосы, освещение, реле)
- **Laravel backend** (API Gateway) с Inertia.js + Vue 3 фронтендом
- **Python микросервисы** (MQTT bridge, history logger, automation engine, scheduler)
- **PostgreSQL + TimescaleDB** для телеметрии и временных рядов
- **MQTT протокол** для связи узлов ↔ backend
- **Android мобильное приложение**
- **Инфраструктура** (Docker, Kubernetes, стек мониторинга)

**Ключевая архитектурная концепция:** Иерархия Теплица → Зоны → Узлы → Каналы. Система использует управление на основе зон, где каждая зона может иметь несколько узлов, а узлы имеют каналы для сенсоров/исполнительных устройств.

## Основная документация

**ВСЕГДА читай это в первую очередь при работе над задачей:**
- `doc_ai/INDEX.md` — главный индекс документации (source of truth)
- `doc_ai/SYSTEM_ARCH_FULL.md` — архитектура системы
- `doc_ai/ARCHITECTURE_FLOWS.md` — **архитектурные схемы и пайплайны** (визуализация потоков данных)
- `doc_ai/DEV_CONVENTIONS.md` — конвенции разработки
- `README.md` — быстрые ссылки и обзор структуры

**Примечание:** `doc_ai/` — это source of truth. `docs/` — это автоматически сгенерированное зеркало, не редактируй его вручную.

### Документация по компонентам

- **Backend:** `doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md`, `backend/README.md`
- **Python сервисы:** `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`, `backend/services/README.md`
- **history-logger API:** `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md` — REST API спецификация
- **Прошивки:** `doc_ai/02_HARDWARE_FIRMWARE/`, `firmware/README.md`
- **MQTT протокол:** `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- **NodeConfig:** `firmware/NODE_CONFIG_SPEC.md`
- **Frontend:** `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md`
- **Android:** `doc_ai/12_ANDROID_APP/`
- **Зоны/Рецепты:** `doc_ai/06_DOMAIN_ZONES_RECIPES/`
- **Effective Targets:** `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` — спецификация контроллеров

## Основные команды разработки

### Сборка и запуск

```bash
# Запустить dev окружение (из корня проекта)
make up
# Или: docker compose -f backend/docker-compose.dev.yml up -d --build

# Остановить dev окружение
make down

# Операции с базой данных
make migrate      # Выполнить миграции
make seed         # Заполнить базу тестовыми данными
make reset-db     # Полная пересборка + заполнение
```

### Тестирование

```bash
# Запустить все тесты (PHP + Python)
make test

# Запустить тесты протокольных контрактов
make protocol-check

# Laravel тесты (внутри контейнера)
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test

# Python тесты (внутри контейнера)
docker compose -f backend/docker-compose.dev.yml exec mqtt-bridge pytest

# Frontend тесты (из backend/laravel/)
npm run test              # Vitest unit тесты
npm run test:ui           # Vitest с UI
npm run e2e               # Playwright E2E тесты
npm run e2e:ci            # E2E тесты для CI
```

### Качество кода

```bash
# PHP линтинг (Pint)
make lint

# Frontend линтинг (из backend/laravel/)
npm run lint
npm run typecheck
```

### Другие инструменты

```bash
# Smoke тесты
make smoke

# Аудит горячих точек
make audit

# Генерация ERD диаграммы
make erd
```

### Доступ к dev сервисам

- Laravel: http://localhost:8080
- mqtt-bridge: http://localhost:9000
- history-logger метрики: http://localhost:9301/metrics
- automation-engine метрики: http://localhost:9401/metrics
- scheduler метрики: http://localhost:9402/metrics
- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090

## Архитектурные особенности

### Архитектура Backend

**Laravel (API Gateway):**
- Технологический стек: Laravel 12 + Inertia.js + Vue 3 + TypeScript
- Обрабатывает REST API, WebSocket (Reverb), аутентификацию (Sanctum)
- Frontend использует Pinia для управления состоянием, ECharts для визуализаций
- Расположен в: `backend/laravel/`

**Python микросервисы** (расположены в `backend/services/`):
- `mqtt-bridge` — FastAPI мост для REST→MQTT (порт 9000)
- `history-logger` — подписчик MQTT, пишет телеметрию в PostgreSQL, **единственная точка публикации команд в MQTT** (порт 9300)
- `automation-engine` — контроллер зон, проверяет targets, отправляет команды через history-logger REST API (порт 9405)
- `scheduler` — обрабатывает расписания полива/освещения из фаз рецептов, отправляет команды через automation-engine REST API (порт 9402)

**Архитектура потока команд:**
```
Scheduler → REST → Automation-Engine → REST → History-Logger → MQTT → Узлы
```

**Критично:** Только `history-logger` публикует команды напрямую в MQTT. Остальные сервисы используют REST API для обеспечения централизованного логирования и мониторинга.

### Архитектура прошивок

- **Язык:** C с фреймворком ESP-IDF
- **Расположение:** `firmware/`
- **Структура:**
  - `common/components/` — общие компоненты (MQTT, WiFi, I2C, OLED, сенсоры, драйверы)
  - `nodes/` — проекты прошивок для конкретных узлов (pump_node, ph_node, ec_node, climate_node, light_node, relay_node)

**Ключевые компоненты:**
- `node_framework` — унифицированный фреймворк для всех узлов (обработка конфига, команд, телеметрии, Safe Mode)
- `mqtt_manager` — MQTT клиент и маршрутизатор топиков
- `config_storage` — сохранение NodeConfig
- Драйверы сенсоров: `trema_ph`, `trema_ec`, `sht3x` (темп/влажность), `ina209` (ток), `ccs811` (CO2)
- Драйверы исполнительных устройств: `pump_driver`, `relay_driver`, `pwm_driver`, `ws2811_driver`

**Система NodeConfig:**
- Узлы получают конфигурацию через MQTT
- Конфигурация хранится в NVS (Non-Volatile Storage)
- Спецификация: `firmware/NODE_CONFIG_SPEC.md`

### MQTT протокол

- **Брокер:** Eclipse Mosquitto (порт 1883)
- **Структура топиков:** Иерархическая с greenhouse_uid/node_uid
- **Типы сообщений:** telemetry, commands, config, heartbeat
- **Полная спецификация:** `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`

### Хранение данных

- **PostgreSQL + TimescaleDB** для телеметрии временных рядов
- **Политики хранения:**
  - Сырые данные: 7-30 дней (настраивается)
  - Агрегированные (1m, 1h, daily): до 12 месяцев
- **Автоматическая агрегация:** Laravel команды `telemetry:cleanup-raw` и `telemetry:aggregate`

### Стек мониторинга

- **Prometheus** (порт 9090) — сбор метрик
- **Grafana** (порт 3000) — дашборды визуализации
- **Alertmanager** (порт 9093) — управление алертами
- Конфигурация: `configs/dev/prometheus.yml`, `configs/dev/alertmanager/`

## Конвенции разработки

### Git Workflow

**Ветки:**
- `main` — стабильная, развертываемая версия
- `feature/<описание-задачи>` — ветки фич

**Формат коммитов:**
```
<тип>: <описание>

Типы: feat, fix, refactor, docs, test, chore
Примеры:
  feat: добавлен mqtt телеметрия энкодер для ph ноды
  fix: исправлена инициализация i2c шины для ec ноды
  docs: расширены шаблоны задач для ai агентов
```

### Стандарты кодирования

**Прошивки (C/ESP-IDF):**
- Файлы: `snake_case.c`, `snake_case.h`
- Функции/переменные: `snake_case`
- Типы/enum: `PascalCase` (например, `PhNodeState`, `MeasurementResult`)
- Макросы/константы: `UPPER_SNAKE_CASE`
- Всегда обрабатывай коды ошибок ESP-IDF
- Используй ESP_LOG с соответствующими тегами и уровнями

**Backend (PHP/Laravel):**
- Следуй конвенциям Laravel (стандарты PSR)
- Используй Pint для форматирования кода: `make lint`
- Четкое разделение слоев: транспорт → бизнес-логика → доступ к данным

**Frontend (Vue 3 + TypeScript):**
- TypeScript strict mode включен
- Используй composition API
- Компонентные тесты с Vitest + Vue Test Utils
- E2E тесты с Playwright
- Запускай `npm run lint` и `npm run typecheck` перед коммитом

**Python сервисы:**
- Следуй конвенциям PEP 8
- Требуются type hints
- Pytest для тестирования
- Расположены в `backend/services/`

### Подход "Документация в первую очередь"

Из `DEV_CONVENTIONS.md`:
1. **Сначала документация** — обнови/создай спецификацию (Markdown)
2. **Определи интерфейс** — заголовки, API контракты, MQTT схемы
3. **Реализуй** — напиши фактический код

### Политика Breaking Changes

**Защищенные границы (НЕТ breaking changes без миграции):**
- ESP32 → MQTT → Python → PostgreSQL → Laravel → Vue пайплайн
- MQTT топики/полезная нагрузка, форматы команд, схемы базы данных
- Обязательные ID, API ответы, Inertia props

**Остальные области:** Breaking changes разрешены без обратной совместимости (проект в активной разработке).

## Правила совместимости и архитектурные ограничения

### Источники истины

- **`doc_ai/`** — source of truth (единственный источник правды), всегда редактируй здесь
- **`docs/`** — автоматически генерируемое зеркало, НЕ редактируй вручную
- **Локальные `AGENTS.md`** — всегда проверяй их наличие в подкаталогах перед работой

### Чек-лист при изменении протоколов/данных

При изменении MQTT протокола, схемы БД или API **ОБЯЗАТЕЛЬНО**:

1. Обновить MQTT спецификации:
   - `doc_ai/03_TRANSPORT_MQTT/MQTT_NAMESPACE.md`
   - `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
   - `doc_ai/03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md`

2. При новых `message_type` или `channel`:
   - Обновить `doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`
   - Обновить обработчики в Python сервисах

3. Обновить `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`

4. При изменении API/Inertia props — обновить соответствующий фронтенд

5. Добавить в commit/PR строку совместимости:
   ```
   Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0
   ```

### Зоны ответственности компонентов

| Компонент | ✅ Разрешено | ❌ Запрещено |
|-----------|-------------|-------------|
| **Laravel** | Добавлять маршруты, модели, миграции, страницы | Менять Inertia формат без обновления Vue; обращаться к MQTT напрямую |
| **Python services** | Алгоритмы контроллеров, обработка MQTT | Менять форматы команд; обходить централизованное логирование |
| **PostgreSQL** | Добавлять таблицы/поля через миграции | Ручной DDL; удалять обязательные поля; циклические FK |
| **MQTT** | Добавлять новые `message_type` | Менять существующие топики/форматы; нарушать иерархию |
| **Frontend (Vue)** | Улучшать UI/UX, добавлять компоненты | Ломать структуру props; игнорировать типы TypeScript |

### Критичные технические запреты

1. **ESP32 прошивки:**
   - НЕ использовать динамическое выделение памяти в горячих путях (критично для стабильности)

2. **Backend:**
   - Laravel НЕ обращается к MQTT напрямую — только через Python-сервисы
   - Все изменения БД ТОЛЬКО через Laravel-миграции (не ручной DDL)

3. **MQTT:**
   - Формат топиков СТРОГО: `hydro/{gh}/{zone}/{node}/{channel}/{message_type}`
   - НЕ менять существующие форматы сообщений без обновления ВСЕГО пайплайна

4. **Команды к узлам:**
   - Отправка ТОЛЬКО через Python/MQTT слой (не обходить scheduler)

### Работа с ИИ-агентами

Для постановки задач ИИ-агентам используй:
- **`doc_ai/TASKS_FOR_AI_AGENTS.md`** — детальные правила формулирования задач
- **`AGENTS.md`** — общие правила для всего репозитория
- **Локальные `AGENTS.md`** в подкаталогах — специфичные правила для компонентов

**Формат задачи должен включать:**
1. Контекст (где в архитектуре, какие документы читать)
2. Цель (что должно измениться)
3. Входные данные (пути к файлам, примеры)
4. Ожидаемый результат (конкретные файлы, функции)
5. Ограничения (что нельзя менять)
6. Критерии приёмки (как проверить)

## Разработка прошивок ESP-IDF

### Настройка окружения ESP-IDF

**Расположение:** `/home/georgiy/esp/esp-idf/`
**Версия:** v5.5.2

Перед работой с прошивками необходимо активировать окружение ESP-IDF:

```bash
# Активация окружения ESP-IDF
source /home/georgiy/esp/esp-idf/export.sh

# Или короткий алиас (добавь в ~/.bashrc или ~/.zshrc для удобства):
alias get_idf='source /home/georgiy/esp/esp-idf/export.sh'
```

После активации окружения станут доступны команды `idf.py` и все необходимые инструменты компиляции.

### Сборка прошивки

```bash
# Активировать окружение ESP-IDF (если еще не активировано)
source /home/georgiy/esp/esp-idf/export.sh

# Перейти в директорию ноды и собрать
cd firmware/nodes/<имя_ноды>
idf.py build
idf.py flash monitor
```

### Основные команды ESP-IDF

```bash
idf.py menuconfig  # Настройка проекта
idf.py build       # Сборка прошивки
idf.py flash       # Прошивка устройства
idf.py monitor     # Просмотр serial вывода
idf.py erase-flash # Очистка flash памяти
```

### Типы узлов

- `pump_node` — управление насосом полива с мониторингом тока
- `ph_node` — измерение pH и управление дозирующим насосом
- `ec_node` — измерение EC/TDS и дозирование питательных веществ
- `climate_node` — мониторинг температуры, влажности, CO2
- `light_node` — управление освещением (PWM/адресные светодиоды)
- `relay_node` — универсальное управление реле

## Разработка Frontend

Расположен в `backend/laravel/resources/js/`

### Ключевые технологии
- Vue 3 (Composition API)
- TypeScript
- Inertia.js (SSR)
- Pinia (управление состоянием)
- Tailwind CSS
- ECharts (визуализации)

### Разработка

```bash
cd backend/laravel

# Dev сервер с HMR
npm run dev

# Сборка для production
npm run build

# Проверка типов
npm run typecheck

# Линтинг
npm run lint
```

### Стратегия тестирования

См. `doc_ai/07_FRONTEND/FRONTEND_TESTING.md` для деталей:
- **Unit тесты:** Vitest для утилит и composables
- **Компонентные тесты:** Vitest + Vue Test Utils
- **Интеграционные тесты:** Тестирование Inertia страниц
- **E2E тесты:** Playwright для критических пользовательских сценариев

## Работа с AI агентами

См. `doc_ai/TASKS_FOR_AI_AGENTS.md` и `AGENTS.md` для детальных руководств.

**Ключевые принципы:**
- Всегда сначала проверяй документацию в `doc_ai/`
- Для нетривиальных задач создавай `.md` файл с формализованными требованиями
- Будь конкретным: указывай файлы, функции, структуры данных, форматы сообщений
- Результаты должны проверяться людьми или валидационными агентами

## Стратегия тестирования

### Тесты протокольных контрактов

```bash
make protocol-check
```

Это запускает:
- Проверки соответствия runtime схем
- Контрактные тесты для MQTT сообщений
- Тесты валидации протокола
- Chaos тесты (неблокирующие)
- Тесты WebSocket событий

### Симулятор узлов

Расположен в `tests/node_sim/` — симулирует ESP32 узлы для интеграционного тестирования без физического оборудования.

### E2E тесты

Расположены в `tests/e2e/` — сквозное тестирование сценариев.

## Мониторинг и наблюдаемость

### Проверка здоровья системы

```bash
./backend/scripts/check_monitoring.sh
```

### Просмотр логов

```bash
# Логи сервиса
docker compose -f backend/docker-compose.dev.yml logs -f <сервис>

# Все логи Python сервисов
docker compose -f backend/docker-compose.dev.yml logs -f mqtt-bridge history-logger automation-engine scheduler
```

См. `backend/docs/LOGS_VIEWING.md` для детального руководства по просмотру логов.

### Endpoints метрик

- history-logger: http://localhost:9301/metrics
- automation-engine: http://localhost:9401/metrics
- scheduler: http://localhost:9402/metrics

### Дашборды Grafana

Доступ по http://localhost:3000 (по умолчанию: admin/admin):
- System Overview — здоровье сервисов
- Zone Telemetry — графики pH/EC/температуры
- Node Status — подключение узлов
- Alerts Dashboard — активные алерты
- Commands & Automation — статистика команд

## Важные замечания

1. **Всегда запускай команды внутри Docker контейнеров** для backend сервисов (используй `docker compose exec`)
2. **ESP-IDF окружение:** Перед работой с прошивками активируй окружение: `source /home/georgiy/esp/esp-idf/export.sh`
3. **MQTT_EXTERNAL_HOST:** В dev по умолчанию `host.docker.internal`. Для реальных ESP32 устройств установи IP адрес хоста
4. **WebSocket/Reverb:** Автоматически запускается в dev (REVERB_AUTO_START=true). Ручной запуск нужен только вне docker-compose
5. **Миграции базы данных:** Запускай `make migrate` после получения изменений схемы
6. **Статус компонентов:** Проверяй README файлы для флагов статуса (PLANNED, IN_PROGRESS, MVP_DONE)
7. **Изменения протокола:** Всегда обновляй контрактные тесты при изменении форматов MQTT сообщений

## Troubleshooting

### Backend не запускается
- Проверь доступность портов (8080, 9000, 9300, 9401, 9402, 1883, 5432)
- Убедись, что Docker daemon запущен
- Проверь логи: `docker compose -f backend/docker-compose.dev.yml logs`

### Сборка прошивки падает
- **Окружение ESP-IDF не активировано:** Запусти `source /home/georgiy/esp/esp-idf/export.sh`
- **Команда idf.py не найдена:** Проверь, что ESP-IDF установлен в `/home/georgiy/esp/esp-idf/` и активирован
- **Ошибки компиляции:** Проверь зависимости компонентов в CMakeLists.txt
- **Ошибки с I2C:** Проверь, что I2C адреса соответствуют твоему оборудованию

### Тесты падают
- Убедись, что dev стек запущен: `make up`
- Проверь, что база данных заполнена: `make seed`
- Проверь доступность MQTT брокера

### Проблемы с подключением MQTT
- Проверь логи MQTT брокера: `docker compose -f backend/docker-compose.dev.yml logs mqtt`
- Проверь учетные данные в конфигурации mosquitto
- Для ESP32: убедись, что MQTT_EXTERNAL_HOST установлен правильно

## Формат ссылок на файлы

При ссылках на места в коде в коммитах или документации используй формат:
```
путь_к_файлу:номер_строки
```

Пример: `src/services/process.ts:712`

Этот формат кликабелен в большинстве IDE и инструментов.
