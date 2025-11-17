Automation Engine — Zone Controller с правилами автоматизации.

Проверяет активные зоны с рецептами:
- Сравнивает текущую телеметрию (`telemetry_last`) с targets из `recipe_phases`
- Публикует команды корректировки pH/EC через MQTT для irrigation нод
- Базовые правила: pH diff > 0.2 → add_base/add_acid, EC diff > 0.2 → add_nutrients/dilute

Получает конфиг из Laravel API (`/api/system/config/full`).

Метрики Prometheus на порту 9401.


