# Обработка config_response от ноды

**Дата:** 2025-11-23

---

## Изменение логики привязки ноды

### Новая логика:
Нода считается привязанной к зоне **только после получения успешного config_response** от ноды, подтверждающего установку конфига.

---

## Поток привязки ноды

1. **Пользователь привязывает ноду к зоне** через UI
   - `NodeService::update()` устанавливает `zone_id`
   - Нода остается в состоянии `REGISTERED_BACKEND`

2. **Срабатывает событие `NodeConfigUpdated`**
   - `PublishNodeConfigOnUpdate` публикует конфиг в MQTT
   - Нода **НЕ** переводится в `ASSIGNED_TO_ZONE` сразу

3. **Нода получает конфиг** из MQTT топика `hydro/{gh}/{zone}/{node}/config`
   - Валидирует конфиг
   - Сохраняет в NVS
   - Применяет конфигурацию

4. **Нода отправляет `config_response`** в топик `hydro/{gh}/{zone}/{node}/config_response`
   - При успехе: `{"status": "OK", ...}`
   - При ошибке: `{"status": "ERROR", "error": "...", ...}`

5. **history-logger обрабатывает `config_response`**
   - Подписан на топик `hydro/+/+/+/config_response`
   - При `status: "OK"`:
     - Проверяет, что нода в `REGISTERED_BACKEND` и имеет `zone_id`
     - Вызывает Laravel API для перевода в `ASSIGNED_TO_ZONE`
   - При `status: "ERROR"`:
     - Логирует ошибку
     - Нода остается в `REGISTERED_BACKEND`

6. **Нода переводится в `ASSIGNED_TO_ZONE`**
   - Только после успешного подтверждения от ноды
   - Нода считается привязанной к зоне

---

## Измененные файлы

### 1. history-logger/main.py
- ✅ Добавлена подписка на `hydro/+/+/+/config_response`
- ✅ Создан обработчик `handle_config_response()`
- ✅ Добавлены метрики для мониторинга

### 2. PublishNodeConfigOnUpdate.php
- ✅ Убран перевод в `ASSIGNED_TO_ZONE` после публикации конфига
- ✅ Оставлена только публикация конфига в MQTT

---

## Преимущества

1. ✅ **Гарантия получения конфига** - нода считается привязанной только после подтверждения
2. ✅ **Надежность** - если конфиг не установился, нода не считается привязанной
3. ✅ **Обратная связь** - система знает, что нода действительно получила и применила конфиг
4. ✅ **Обработка ошибок** - если установка конфига не удалась, нода остается в `REGISTERED_BACKEND`

---

## Метрики

Добавлены Prometheus метрики:
- `config_response_received_total` - всего получено config_response
- `config_response_success_total{node_uid}` - успешных config_response по нодам
- `config_response_error_total{node_uid}` - ошибок config_response по нодам
- `config_response_processed_total` - обработано config_response

---

## Важные замечания

- Откат привязки при ошибке публикации конфига остается в `PublishNodeConfigOnUpdate`
- Если нода не отправила `config_response`, она не будет переведена в `ASSIGNED_TO_ZONE`
- Нода должна быть в состоянии `REGISTERED_BACKEND` и иметь `zone_id` для перевода

