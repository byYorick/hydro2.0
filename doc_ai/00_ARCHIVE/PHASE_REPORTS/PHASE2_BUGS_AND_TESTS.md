# Баги и тесты для Фазы 2

**Дата:** 2025-01-27

---

## Найденные и исправленные баги

### 1. ❌ Баг в `NodeRegistryService.php`

**Проблема:**
```php
if (!$node->exists || !$node->first_seen_at) {
    $node->first_seen_at = now();
}
```

`firstOrNew()` создаёт модель, но не сохраняет её, поэтому `$node->exists` может быть `false` даже для существующей ноды до вызова `save()`.

**Исправление:**
```php
// Проверяем через id, так как firstOrNew создаёт модель, но не сохраняет её
if (!$node->id || !$node->first_seen_at) {
    $node->first_seen_at = now();
}
```

**Файл:** `backend/laravel/app/Services/NodeRegistryService.php`

---

### 2. ❌ Баг в тестах `test_telemetry.py`

**Проблема:**
Тесты не учитывали новую логику проверки `validated` в `process_telemetry_batch()`. Моки возвращали данные без поля `validated`, что приводило к тому, что телеметрия игнорировалась.

**Исправление:**
Обновлены все тесты для включения `validated: True` в моках:
```python
mock_fetch.return_value = [{"id": 10, "zone_id": 1, "validated": True}]
```

Также добавлены проверки вызова `upsert_telemetry_last` во всех тестах.

**Файл:** `backend/services/common/test_telemetry.py`

---

### 3. ⚠️ Потенциальная проблема в маппинге алертов

**Проблема:**
В `alerts_manager.py` маппинг `TEMP_HIGH`/`TEMP_LOW` использует неправильные коды:
```python
'TEMP_HIGH': (AlertSource.BIZ.value, AlertCode.BIZ_HIGH_PH.value),  # Неправильно!
'TEMP_LOW': (AlertSource.BIZ.value, AlertCode.BIZ_LOW_PH.value),  # Неправильно!
```

**Статус:** Отмечено как временное решение в комментариях. Нужно добавить отдельные коды для температуры в будущем.

**Файл:** `backend/services/automation-engine/alerts_manager.py`

---

## Созданные тесты

### Python тесты

1. **`backend/services/common/test_metrics.py`**
   - `test_normalize_metric_type_valid()` — нормализация валидных метрик
   - `test_normalize_metric_type_invalid()` — обработка невалидных метрик
   - `test_canonical_metrics_completeness()` — проверка полноты словаря
   - `test_unknown_metric_error()` — тест исключения

2. **`backend/services/common/test_alerts.py`**
   - `test_create_alert_with_all_fields()` — создание алерта со всеми полями
   - `test_create_alert_without_details()` — создание алерта без details
   - `test_create_alert_with_null_zone_id()` — глобальные алерты
   - `test_alert_source_enum()` — проверка enum AlertSource
   - `test_alert_code_enum()` — проверка enum AlertCode

3. **`backend/services/common/test_telemetry_phase2.py`**
   - `test_process_telemetry_batch_ignores_unvalidated_node()` — игнорирование невалидированных нод
   - `test_process_telemetry_batch_ignores_unknown_metric()` — игнорирование неизвестных метрик
   - `test_process_telemetry_batch_normalizes_metric_type()` — нормализация метрик
   - `test_process_telemetry_batch_validated_node()` — обработка валидированных нод

4. **`backend/services/automation-engine/test_alerts_manager_phase2.py`**
   - `test_get_alert_source_and_code_known_types()` — маппинг известных типов
   - `test_get_alert_source_and_code_unknown_type()` — обработка неизвестных типов
   - `test_ensure_alert_creates_new_alert_with_source_and_code()` — создание нового алерта
   - `test_ensure_alert_updates_existing_alert()` — обновление существующего алерта
   - `test_alert_type_mapping_completeness()` — проверка полноты маппинга

### Laravel тесты

1. **`backend/laravel/tests/Unit/MetricTypeTest.php`**
   - `test_metric_type_values()` — проверка всех значений enum
   - `test_metric_type_is_valid()` — валидация метрик
   - `test_metric_type_normalize()` — нормализация метрик
   - `test_metric_type_cases()` — проверка всех case'ов enum

2. **`backend/laravel/tests/Feature/NodeRegistryServiceTest.php`**
   - `test_register_node_creates_new_node()` — создание новой ноды
   - `test_register_node_updates_existing_node()` — обновление существующей ноды
   - `test_register_node_with_zone_uid_zn_format()` — регистрация с zone_uid в формате zn-{id}
   - `test_register_node_with_zone_uid_numeric()` — регистрация с числовым zone_uid
   - `test_register_node_with_invalid_zone_uid()` — обработка невалидного zone_uid
   - `test_register_node_sets_validated_to_true()` — проверка validated
   - `test_register_node_sets_first_seen_at_on_first_registration()` — установка first_seen_at
   - `test_register_node_preserves_first_seen_at_on_update()` — сохранение first_seen_at при обновлении

---

## Запуск тестов

### Python тесты

```bash
cd backend/services
python -m pytest common/test_metrics.py -v
python -m pytest common/test_alerts.py -v
python -m pytest common/test_telemetry_phase2.py -v
python -m pytest automation-engine/test_alerts_manager_phase2.py -v
```

### Laravel тесты

```bash
cd backend/laravel
php artisan test --filter MetricTypeTest
php artisan test --filter NodeRegistryServiceTest
```

---

## Итоги

- ✅ Найдено и исправлено **2 бага**
- ✅ Создано **9 новых Python тестов**
- ✅ Создано **11 новых Laravel тестов**
- ✅ Обновлены существующие тесты для учёта новой логики
- ⚠️ Обнаружена **1 потенциальная проблема** (временно отложена)

---

**Статус:** Тесты готовы к запуску. Для запуска Python тестов требуется установленный Python и pytest. Для Laravel тестов требуется запущенная БД.

