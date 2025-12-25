# Этап 2.2: EffectiveTargetsService — единый контракт для Python

**Дата:** 2025-12-25  
**Статус:** ✅ Завершено

## Цель этапа

Создать сервис для вычисления эффективных целевых параметров цикла выращивания, который объединяет параметры из текущей фазы рецепта и активные перекрытия (overrides).

## Реализация

### ✅ EffectiveTargetsService

**Файл:** `app/Services/EffectiveTargetsService.php`

#### Основные методы:

1. **`getEffectiveTargets(int $growCycleId): array`**
   - Получает эффективные целевые параметры для одного цикла
   - Возвращает структурированный JSON согласно контракту
   - Выбрасывает исключение, если цикл не найден или нет текущей фазы

2. **`getEffectiveTargetsBatch(array $growCycleIds): array`**
   - Получает эффективные параметры для нескольких циклов
   - Возвращает массив результатов, ключ - grow_cycle_id
   - Обрабатывает ошибки для каждого цикла отдельно

#### Внутренние методы:

- **`extractPhaseTargets(RecipeRevisionPhase $phase): array`**
  - Извлекает целевые параметры из фазы рецепта
  - Поддерживает все типы параметров: ph, ec, irrigation, mist, lighting, climate_request, extensions

- **`getActiveOverrides(GrowCycle $cycle): Collection`**
  - Получает активные перекрытия для цикла
  - Фильтрует по `is_active` и времени действия (`applies_from`, `applies_until`)

- **`mergeOverrides(array $phaseTargets, Collection $overrides): array`**
  - Сливает перекрытия с базовыми параметрами
  - Поддерживает вложенные параметры (например, `ph.target`, `irrigation.interval_sec`)

- **`calculatePhaseDueAt(GrowCycle $cycle, RecipeRevisionPhase $phase): ?Carbon`**
  - Вычисляет дату окончания фазы на основе `progress_model`
  - Поддерживает модели: TIME, TIME_WITH_TEMP_CORRECTION
  - GDD требует отдельного сервиса (Phase Progress Engine)

- **`calculateSpeedFactor(GrowCycle $cycle, RecipeRevisionPhase $phase): ?float`**
  - Вычисляет коэффициент скорости роста на основе температуры
  - Используется для TIME_WITH_TEMP_CORRECTION

- **`cleanNullValues(array $array): array`**
  - Рекурсивно очищает null значения из массива targets
  - Удаляет пустые массивы для чистого JSON

## Контракт JSON

Сервис возвращает структурированный JSON согласно плану:

```json
{
  "cycle_id": 123,
  "zone_id": 5,
  "phase": {
    "id": 77,
    "code": "VEG",
    "name": "Вегетация",
    "started_at": "2025-12-25T10:00:00Z",
    "due_at": "2025-12-30T10:00:00Z",
    "progress_model": "TIME"
  },
  "targets": {
    "ph": {
      "target": 5.8,
      "min": 5.6,
      "max": 6.0
    },
    "ec": {
      "target": 1.6,
      "min": 1.4,
      "max": 1.8
    },
    "irrigation": {
      "mode": "SUBSTRATE",
      "interval_sec": 3600,
      "duration_sec": 300
    },
    "mist": {
      "interval_sec": 7200,
      "duration_sec": 60,
      "mode": "NORMAL"
    },
    "lighting": {
      "photoperiod_hours": 16,
      "start_time": "06:00:00"
    },
    "climate_request": {
      "temp_air_target": 24.0,
      "humidity_target": 65.0,
      "co2_target": 800
    }
  }
}
```

## Поддерживаемые параметры

### Обязательные (MVP):
- ✅ `ph` - pH параметры (target, min, max)
- ✅ `ec` - EC параметры (target, min, max)
- ✅ `irrigation` - Полив (mode, interval_sec, duration_sec)

### Опциональные:
- ✅ `mist` - Туман (interval_sec, duration_sec, mode)
- ✅ `lighting` - Освещение (photoperiod_hours, start_time)
- ✅ `climate_request` - Запрос к климату теплицы (temp_air_target, humidity_target, co2_target)
- ✅ `extensions` - Расширения (нестандартные параметры из JSONB)

## Перекрытия (Overrides)

### Поддержка вложенных параметров:
- `ph.target` - перекрытие целевого pH
- `ph.min` - перекрытие минимального pH
- `irrigation.interval_sec` - перекрытие интервала полива
- И т.д.

### Логика применения:
1. Базовые параметры берутся из текущей фазы рецепта
2. Активные перекрытия применяются поверх базовых
3. Перекрытия проверяются по времени (`applies_from`, `applies_until`)
4. Типизация значений согласно `value_type` (integer, decimal, boolean, time)

## Вычисление due_at

### Модель TIME:
- Использует `duration_hours` или `duration_days` из фазы
- Простое добавление времени к `phase_started_at`

### Модель TIME_WITH_TEMP_CORRECTION:
- Использует `temp_avg_24h` из `progress_meta`
- Вычисляет `speed_factor` на основе разницы с `base_temp_c`
- Корректирует длительность фазы

### Модель GDD:
- Требует накопления данных о температуре
- Будет реализована в Phase Progress Engine (Этап 3.2)

## Использование

```php
use App\Services\EffectiveTargetsService;

$service = new EffectiveTargetsService();

// Для одного цикла
$targets = $service->getEffectiveTargets($growCycleId);

// Для нескольких циклов (batch)
$targets = $service->getEffectiveTargetsBatch([1, 2, 3]);
```

## Следующие шаги

1. ✅ EffectiveTargetsService создан
2. ⏭️ **Этап 2.3:** Создание API эндпоинтов для использования сервиса
3. ⏭️ **Этап 3.1:** Создание batch-endpoint `/api/internal/effective-targets/batch` для Python сервисов

## Acceptance Criteria

- ✅ Сервис возвращает структурированный JSON согласно контракту
- ✅ Поддерживаются все типы параметров из плана
- ✅ Перекрытия корректно применяются к базовым параметрам
- ✅ Вычисление due_at работает для TIME и TIME_WITH_TEMP_CORRECTION
- ✅ Batch-метод обрабатывает множественные запросы
- ✅ Null значения очищаются из результата

---

**Примечание:** GDD модель требует отдельного сервиса Phase Progress Engine, который будет создан на Этапе 3.2.

