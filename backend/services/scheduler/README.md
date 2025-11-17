Scheduler — планировщик поливов и освещения.

Читает расписания из `recipe_phases.targets`:
- `irrigation_schedule`: список времени поливов (например, `["08:00", "14:00", "20:00"]`)
- `lighting_schedule`: окно освещения (например, `"06:00-22:00"`)

Публикует команды на MQTT для irrigation/lighting нод.

Метрики Prometheus на порту 9402.

