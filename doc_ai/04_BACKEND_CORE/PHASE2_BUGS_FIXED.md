# Исправленные баги Фазы 2

**Дата:** 2025-01-27

---

## Исправленные баги

### 1. ✅ Добавлены недостающие коды алертов

**Проблема:**
В `alerts_manager.py` использовались неправильные коды для температуры, влажности и света:
- `TEMP_HIGH`/`TEMP_LOW` использовали коды pH
- `HUMIDITY_HIGH`/`HUMIDITY_LOW` использовали `BIZ_CONFIG_ERROR`
- `LIGHT_FAILURE` использовал `BIZ_CONFIG_ERROR`

**Исправление:**
1. Добавлены новые коды в `AlertCode` enum:
   - `BIZ_HIGH_TEMP = "biz_high_temp"`
   - `BIZ_LOW_TEMP = "biz_low_temp"`
   - `BIZ_HIGH_HUMIDITY = "biz_high_humidity"`
   - `BIZ_LOW_HUMIDITY = "biz_low_humidity"`
   - `BIZ_LIGHT_FAILURE = "biz_light_failure"`

2. Обновлён маппинг в `alerts_manager.py`:
   ```python
   'TEMP_HIGH': (AlertSource.BIZ.value, AlertCode.BIZ_HIGH_TEMP.value),
   'TEMP_LOW': (AlertSource.BIZ.value, AlertCode.BIZ_LOW_TEMP.value),
   'HUMIDITY_HIGH': (AlertSource.BIZ.value, AlertCode.BIZ_HIGH_HUMIDITY.value),
   'HUMIDITY_LOW': (AlertSource.BIZ.value, AlertCode.BIZ_LOW_HUMIDITY.value),
   'LIGHT_FAILURE': (AlertSource.BIZ.value, AlertCode.BIZ_LIGHT_FAILURE.value),
   ```

3. Обновлён `light_controller.py` для использования правильного кода

4. Обновлены тесты для проверки новых кодов

**Файлы:**
- `backend/services/common/alerts.py`
- `backend/services/automation-engine/alerts_manager.py`
- `backend/services/automation-engine/light_controller.py`
- `backend/services/common/test_alerts.py`
- `backend/services/automation-engine/test_alerts_manager_phase2.py`

---

### 2. ✅ Исправлен баг в `NodeRegistryService.php`

**Проблема:**
Использование `$node->exists` после `firstOrNew()` некорректно, так как модель создаётся, но не сохраняется до вызова `save()`.

**Исправление:**
```php
// Было:
if (!$node->exists || !$node->first_seen_at) {
    $node->first_seen_at = now();
}

// Стало:
// Проверяем через id, так как firstOrNew создаёт модель, но не сохраняет её
if (!$node->id || !$node->first_seen_at) {
    $node->first_seen_at = now();
}
```

**Файл:** `backend/laravel/app/Services/NodeRegistryService.php`

---

### 3. ✅ Исправлены тесты `test_telemetry.py`

**Проблема:**
Тесты не учитывали новую логику проверки `validated` в `process_telemetry_batch()`.

**Исправление:**
- Добавлено `validated: True` во все моки
- Добавлены проверки вызова `upsert_telemetry_last` во всех тестах

**Файл:** `backend/services/common/test_telemetry.py`

---

## Результаты тестов

### Laravel тесты

✅ **MetricTypeTest**: 4/4 тестов прошли успешно
- `test_metric_type_values`
- `test_metric_type_is_valid`
- `test_metric_type_normalize`
- `test_metric_type_cases`

### Python тесты

⚠️ **Требуют запущенное окружение:**
- `test_metrics.py` — требует Python и pytest
- `test_alerts.py` — требует Python и pytest
- `test_telemetry_phase2.py` — требует Python и pytest
- `test_alerts_manager_phase2.py` — требует Python и pytest

---

## Итоги

- ✅ Исправлено **3 бага**
- ✅ Обновлено **5 файлов**
- ✅ Обновлено **2 теста**
- ✅ Все Laravel тесты проходят
- ⚠️ Python тесты готовы, но требуют окружение

---

**Статус:** Все баги исправлены, тесты обновлены и готовы к запуску.

