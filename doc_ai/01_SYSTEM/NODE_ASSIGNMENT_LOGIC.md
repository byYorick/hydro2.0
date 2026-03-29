# Логика привязки ноды к зоне

**Дата:** 2025-11-23


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## Изменение логики

### Старая логика:
1. При установке `zone_id` нода сразу переводилась в `ASSIGNED_TO_ZONE`
2. Конфиг публиковался асинхронно через событие
3. Если публикация не удалась, нода все равно считалась привязанной

### Новая логика:
1. При установке `zone_id` нода остается в `REGISTERED_BACKEND`
2. Нода отправляет `config_report` при подключении
3. **Только после получения `config_report`** нода переводится в `ASSIGNED_TO_ZONE`
4. Сервер не публикует конфиги на ноды

---

## Измененные файлы

### 1. NodeService::update()
- Убрана автоматическая установка `ASSIGNED_TO_ZONE` при привязке к зоне
- Нода остается в `REGISTERED_BACKEND` до получения `config_report`

### 2. history-logger::handle_config_report
- Обрабатывает `config_report` от ноды
- Сохраняет `nodes.config`, синхронизирует `node_channels`
- Сообщает Laravel observed-факт `config_report`

### 3. NodeConfigReportObserverService
- Laravel-owner сервис финализации bind/rebind
- Проверяет совпадение `gh_uid/zone_uid` с целевой зоной
- Выполняет `pending_zone_id -> zone_id`
- Переводит ноду в `ASSIGNED_TO_ZONE`

### 4. NodeRegistryService::registerNodeFromHello()
- Убрана автоматическая установка `ASSIGNED_TO_ZONE`
- Всегда оставляет ноду в `REGISTERED_BACKEND`

### 5. NodeSwapService
- Убрана автоматическая установка `ASSIGNED_TO_ZONE` при swap
- Нода остается в `REGISTERED_BACKEND` до получения `config_report`

### 6. Frontend (Add.vue)
- Обновлено сообщение об успешной привязке
- Показывает ожидание `config_report` от ноды

---

## Поток привязки ноды

1. Пользователь привязывает ноду к зоне через UI
2. `NodeService::update()` запускает bind/rebind через `pending_zone_id`, оставляя узел в `REGISTERED_BACKEND`
3. Нода подключается и отправляет `config_report` в `hydro/{gh}/{zone}/{node}/config_report`
4. **history-logger обрабатывает `config_report`:**
   - сохраняет NodeConfig и синхронизирует каналы
   - сообщает Laravel observed-факт
5. **Laravel завершает bind/rebind:**
   - валидирует namespace observed `config_report`
   - переводит `pending_zone_id -> zone_id`
   - переводит ноду в `ASSIGNED_TO_ZONE`
6. Нода считается привязанной

---

## Преимущества

1. ✅ Нода считается привязанной только после `config_report`
2. ✅ Сервер использует актуальный конфиг, присланный нодой
3. ✅ Нет риска рассинхронизации из-за публикации конфига с сервера
4. ✅ Привязка подтверждается фактическим подключением ноды

---

## Важные замечания

- Нода должна быть в состоянии `REGISTERED_BACKEND` для привязки к зоне
