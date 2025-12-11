# Automation Engine

Система автоматизации управления параметрами теплиц с поддержкой параллельной обработки зон, централизованной обработкой ошибок и модульной архитектурой.

## 🏗️ Архитектура

### Слоистая архитектура

```
┌─────────────────────────────────────┐
│         main.py (Entry Point)        │
│  - Конфигурация из Laravel API      │
│  - Параллельная обработка зон       │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│   ZoneAutomationService (Service)    │
│  - Оркестрация обработки зоны        │
│  - Координация контроллеров          │
└──────────────┬──────────────────────┘
               │
    ┌──────────┴──────────┐
    │                     │
┌───▼────────┐    ┌───────▼──────────┐
│ Controllers│    │  Repositories    │
│ - pH/EC    │    │  - Zone          │
│ - Climate  │    │  - Telemetry     │
│ - Light    │    │  - Node          │
│ - Irrigation│   │  - Recipe        │
└───┬────────┘    └───────┬──────────┘
    │                     │
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │   Infrastructure    │
    │  - CommandBus (REST)│
    │  - Error Handler    │
    │  - Retry Mechanism  │
    └─────────────────────┘
```

### Основные компоненты

#### 1. **Services** (`services/`)
- `ZoneAutomationService` - оркестрация обработки зоны, координация всех контроллеров

#### 2. **Repositories** (`repositories/`)
- `ZoneRepository` - доступ к данным зон и capabilities
- `TelemetryRepository` - доступ к телеметрии
- `NodeRepository` - доступ к узлам
- `RecipeRepository` - доступ к рецептам и фазам

#### 3. **Controllers** (корневая директория)
- `CorrectionController` - универсальный контроллер для pH/EC корректировки
- `ClimateController` - управление климатом (температура, влажность, CO₂)
- `LightController` - управление освещением и фотопериодом
- `IrrigationController` - управление поливом и рециркуляцией

#### 4. **Infrastructure** (`infrastructure/`)
- `CommandBus` - централизованная публикация команд через history-logger REST API
- `error_handler.py` - централизованная обработка ошибок
- `exceptions.py` - кастомные исключения
- `utils/retry.py` - retry механизм для критических операций

#### 5. **Configuration** (`config/`)
- `settings.py` - централизованные настройки (пороги, интервалы, множители)

## 🚀 Возможности

### Основной функционал
- ✅ Параллельная обработка зон (до 5 одновременно)
- ✅ Batch запросы к БД (оптимизация производительности)
- ✅ Автоматическая корректировка pH/EC
- ✅ Управление климатом (температура, влажность, вентиляция)
- ✅ Управление освещением (фотопериод, интенсивность)
- ✅ Управление поливом и рециркуляцией
- ✅ Мониторинг здоровья зон (health score)
- ✅ Автоматические переходы между фазами рецепта

### Надежность
- ✅ Централизованная обработка ошибок
- ✅ Retry механизм для критических операций
- ✅ Валидация входных данных
- ✅ Кастомные исключения с контекстом
- ✅ Структурированное логирование

### Производительность
- ✅ Параллельная обработка зон (ускорение в 3-5 раз)
- ✅ Batch запросы к БД (снижение нагрузки на 40-50%)
- ✅ Оптимизированные SQL запросы с CTE

## 📦 Установка

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск
python main.py
```

## ⚙️ Конфигурация

Настройки находятся в `config/settings.py`:

```python
from config.settings import get_settings

settings = get_settings()
print(settings.MAIN_LOOP_SLEEP_SECONDS)  # 15
print(settings.MAX_CONCURRENT_ZONES)     # 5
print(settings.PH_CORRECTION_THRESHOLD)  # 0.2
```

### Основные настройки

- `MAIN_LOOP_SLEEP_SECONDS` - интервал между циклами обработки (по умолчанию: 15)
- `MAX_CONCURRENT_ZONES` - максимальное количество параллельно обрабатываемых зон (по умолчанию: 5)
- `PH_CORRECTION_THRESHOLD` - минимальная разница для корректировки pH (по умолчанию: 0.2)
- `EC_CORRECTION_THRESHOLD` - минимальная разница для корректировки EC (по умолчанию: 0.2)
- `PH_DOSING_MULTIPLIER` - множитель для расчета дозировки pH (по умолчанию: 10.0)
- `EC_DOSING_MULTIPLIER` - множитель для расчета дозировки EC (по умолчанию: 100.0)

## 🧪 Тестирование

```bash
# Запуск всех тестов
pytest automation-engine/ -v

# Запуск конкретного теста
pytest automation-engine/test_correction_controller.py -v

# С покрытием кода
pytest automation-engine/ --cov=automation-engine --cov-report=html
```

### Покрытие тестами

- **72+ тестов** покрывают основные компоненты
- **100% покрытие** для новых компонентов (exceptions, error_handler, config, retry)
- **Основные контроллеры** покрыты тестами
- **Репозитории** покрыты тестами с моками БД

## 📊 Метрики Prometheus

Метрики доступны на порту 9401 (настраивается в `config/settings.py`):

- `automation_loop_errors_total` - ошибки в главном цикле
- `config_fetch_errors_total` - ошибки получения конфигурации
- `config_fetch_success_total` - успешные получения конфигурации
- `zone_checks_total` - количество проверок зон
- `zone_check_seconds` - длительность проверки зоны
- `automation_commands_sent_total{zone_id, metric}` - отправленные команды
- `rest_command_errors_total{error_type}` - ошибки REST запросов к history-logger
- `command_rest_latency_seconds` - задержка REST запросов
- `automation_errors_total` - общие ошибки автоматизации

## 🔧 Использование

### Базовое использование

```python
from services import ZoneAutomationService
from repositories import ZoneRepository, TelemetryRepository, NodeRepository, RecipeRepository
from infrastructure import CommandBus

# Инициализация
zone_repo = ZoneRepository()
telemetry_repo = TelemetryRepository()
node_repo = NodeRepository()
recipe_repo = RecipeRepository()

# CommandBus использует REST API для публикации команд
history_logger_url = "http://history-logger:9300"
history_logger_token = os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN")
command_bus = CommandBus(
    mqtt=None,  # Deprecated, не используется
    gh_uid="gh-1",
    history_logger_url=history_logger_url,
    history_logger_token=history_logger_token
)

# Создание сервиса
zone_service = ZoneAutomationService(
    zone_repo, telemetry_repo, node_repo, recipe_repo, command_bus
)

# Обработка зоны
await zone_service.process_zone(zone_id=1)
```

### Использование CorrectionController

```python
from correction_controller import CorrectionController, CorrectionType

# Создание контроллера для pH
ph_controller = CorrectionController(CorrectionType.PH)

# Проверка и корректировка
command = await ph_controller.check_and_correct(
    zone_id=1,
    targets={"ph": 6.5},
    telemetry={"PH": 6.2},
    nodes={"irrig:default": {"node_uid": "nd-1", "channel": "default", "type": "irrig"}},
    water_level_ok=True
)

# Применение корректировки
if command:
    await ph_controller.apply_correction(command, command_bus)
```

### Обработка ошибок

```python
from error_handler import handle_zone_error, error_handler
from exceptions import ZoneNotFoundError

# Ручная обработка
try:
    await zone_service.process_zone(1)
except Exception as e:
    handle_zone_error(1, e, {"action": "process_zone"})

# Автоматическая обработка через декоратор
@error_handler(zone_id=1, default_return=None)
async def process_zone_safe(zone_id: int):
    await zone_service.process_zone(zone_id)
```

## 📁 Структура проекта

```
automation-engine/
├── main.py                      # Точка входа
├── config/                      # Конфигурация
│   ├── __init__.py
│   └── settings.py              # Настройки
├── repositories/                # Слой доступа к данным
│   ├── __init__.py
│   ├── zone_repository.py
│   ├── telemetry_repository.py
│   ├── node_repository.py
│   └── recipe_repository.py
├── services/                    # Сервисный слой
│   ├── __init__.py
│   └── zone_automation_service.py
├── infrastructure/              # Инфраструктура
│   ├── __init__.py
│   ├── command_bus.py          # REST API для команд
│   ├── command_validator.py    # Валидация команд
│   ├── command_tracker.py      # Отслеживание команд
│   └── command_audit.py        # Аудит команд
├── api.py                       # REST API для scheduler
├── utils/                       # Утилиты
│   ├── __init__.py
│   └── retry.py
├── exceptions.py                # Кастомные исключения
├── error_handler.py             # Обработка ошибок
├── correction_controller.py     # Контроллер pH/EC
├── climate_controller.py       # Контроллер климата
├── light_controller.py          # Контроллер освещения
├── irrigation_controller.py    # Контроллер полива
├── health_monitor.py            # Мониторинг здоровья
├── alerts_manager.py            # Управление алертами
├── recipe_utils.py              # Утилиты рецептов
├── correction_cooldown.py      # Cooldown для корректировок
└── test_*.py                    # Тесты
```

## 🔄 История рефакторинга

Проект прошел полный рефакторинг с улучшением архитектуры, производительности и надежности:

- ✅ **Этап A**: Исправление критических багов
- ✅ **Этап B**: Выделение Correction Controller (убрано 200+ строк дублирования)
- ✅ **Этап C**: Создание слоя репозиториев
- ✅ **Этап D**: Создание сервисного слоя
- ✅ **Этап E**: Оптимизация производительности (параллелизм, batch запросы)
- ✅ **Этап F**: Улучшение качества кода (конфигурация, обработка ошибок)
- ✅ **Этап G**: Тестирование (72+ тестов)

Подробности в `REFACTORING_PLAN.md`.

## 📈 Улучшения производительности

| Метрика | До | После | Улучшение |
|---------|-----|-------|-----------|
| Время обработки 10 зон | ~2.5 мин | ~30 сек | **5x** |
| Запросов к БД на зону | 4+ | 1-2 | **50-75%** |
| Нагрузка на БД | Высокая | Средняя | **40-50%** |

## 📝 Лицензия

Внутренний проект компании.
