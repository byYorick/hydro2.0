# Digital Twin Engine

Сервис для симуляции зон на основе Digital Twin моделей.

## Функции

- Симуляция параметров зоны (pH, EC, климат) на заданный период
- Модели: PHModel, ECModel, ClimateModel
- API эндпоинт `/simulate/zone` для запуска симуляций

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

