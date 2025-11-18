# Digital Twin Engine

Сервис для симуляции зон на основе Digital Twin моделей.

## Функции

- Симуляция параметров зоны (pH, EC, климат) на заданный период
- Модели: PHModel, ECModel, ClimateModel
- Калибровка моделей по историческим данным
- API эндпоинты:
  - `/simulate/zone` — запуск симуляции
  - `/calibrate/zone/{zone_id}` — калибровка моделей для зоны

## Запуск

```bash
python main.py
```

Сервис запускается на порту 8003, метрики Prometheus на порту 9403.

## API

### POST /simulate/zone

Запустить симуляцию зоны.

Тело запроса:
```json
{
  "zone_id": 1,
  "duration_hours": 72,
  "step_minutes": 10,
  "scenario": {
    "recipe_id": 3,
    "initial_state": {
      "ph": 6.0,
      "ec": 1.2,
      "temp_air": 22,
      "temp_water": 20,
      "humidity_air": 60
    }
  }
}
```

Ответ:
```json
{
  "status": "ok",
  "data": {
    "points": [
      {
        "t": 0,
        "ph": 6.0,
        "ec": 1.2,
        "temp_air": 22.0,
        "temp_water": 20.0,
        "humidity_air": 60.0,
        "phase_index": 0
      }
    ],
    "duration_hours": 72,
    "step_minutes": 10
  }
}
```

### POST /calibrate/zone/{zone_id}

Калибровка параметров моделей по историческим данным зоны.

Параметры запроса:
- `days` (query, опционально): Количество дней исторических данных для анализа (по умолчанию 7)

Ответ:
```json
{
  "status": "ok",
  "data": {
    "zone_id": 1,
    "calibrated_at": "2025-01-27T12:00:00",
    "data_period_days": 7,
    "models": {
      "ph": {
        "buffer_capacity": 0.1,
        "natural_drift": 0.012,
        "correction_rate": 0.048
      },
      "ec": {
        "evaporation_rate": 0.018,
        "dilution_rate": 0.01,
        "nutrient_addition_rate": 0.032
      },
      "climate": {
        "heat_loss_rate": 0.52,
        "humidity_decay_rate": 0.019,
        "ventilation_cooling": 1.0
      }
    }
  }
}
```

**Примечание:** Калибровка анализирует:
- Для pH: естественный дрифт и скорость коррекции после дозировок
- Для EC: скорость испарения и добавления питательных веществ
- Для климата: потери тепла и снижение влажности

Если данных недостаточно, возвращаются значения по умолчанию.

