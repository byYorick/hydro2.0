# Исправленные баги в цепочке добавления ноды

**Дата:** 2025-01-27

---

## Резюме

Исправлены все найденные критические баги в цепочке добавления новой ноды и её перехода в рабочий режим.

---

## Исправленные баги

### ✅ БАГ #1: Хардкод временного топика в handle_config_response

**Файл:** `backend/services/history-logger/main.py:1801-1819`

**Проблема:**
- Временный топик хардкодился как `gh-temp/zn-temp`
- Должен использовать реальные `gh_uid` и `zone_uid` из базы данных

**Исправление:**
```python
# Получаем gh_uid и zone_uid из node (уже загружены в запросе к БД)
gh_uid = node.get("gh_uid")
zone_uid = node.get("zone_uid")

if hardware_id and gh_uid and zone_uid:
    # Используем реальные gh_uid и zone_uid вместо хардкода
    temp_topic = f"hydro/{gh_uid}/{zone_uid}/{hardware_id}/config"
```

**Статус:** ✅ Исправлено

---

### ✅ БАГ #2: Дублирование публикации конфига

**Файл:** `backend/laravel/app/Services/NodeService.php:172-177`

**Проблема:**
- Конфиг публиковался дважды: через `PublishNodeConfigJob::dispatch()` и через событие `NodeConfigUpdated`
- Это приводило к двойной публикации конфига

**Исправление:**
- Убрана дублирующая публикация из `NodeService::update()`
- Публикация происходит только через событие `NodeConfigUpdated` в `DeviceNode::saved`
- Это гарантирует единообразную обработку всех случаев

**Статус:** ✅ Исправлено

---

### ✅ БАГ #3: Состояние не сбрасывается при повторном node_hello после отвязки

**Файл:** `backend/laravel/app/Services/NodeRegistryService.php:215-224`

**Проблема:**
- Если узел был отвязан от зоны, но состояние осталось `ASSIGNED_TO_ZONE` или `ACTIVE`
- При повторном `node_hello` состояние не сбрасывалось в `REGISTERED_BACKEND`

**Исправление:**
```php
// Если узел отвязан (zone_id = null), сбрасываем состояние
if (!$node->zone_id && !$node->pending_zone_id) {
    // Узел отвязан - сбрасываем в REGISTERED_BACKEND
    $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
    Log::info('NodeRegistryService: Reset lifecycle_state to REGISTERED_BACKEND for unbound node', [...]);
} elseif (!$node->lifecycle_state) {
    // Новый узел - всегда REGISTERED_BACKEND
    $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
}
```

**Статус:** ✅ Исправлено

---

### ✅ БАГ #4: Нет отката pending_zone_id при ошибке публикации конфига

**Файл:** `backend/laravel/app/Jobs/PublishNodeConfigJob.php:292-323`

**Проблема:**
- Если `PublishNodeConfigJob` провалился после всех попыток, `pending_zone_id` оставался установленным
- Узел "зависал" в процессе привязки
- Пользователь не мог повторно привязать узел

**Исправление:**
```php
public function failed(\Throwable $exception): void
{
    // ... логирование ошибки ...
    
    // Откатываем pending_zone_id при ошибке публикации
    try {
        DB::transaction(function () {
            $node = DeviceNode::where('id', $this->nodeId)
                ->lockForUpdate()
                ->first();
                
            if ($node && $node->pending_zone_id && !$node->zone_id) {
                // Если конфиг не был опубликован, откатываем привязку
                $node->pending_zone_id = null;
                $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
                $node->save();
                
                Log::warning('PublishNodeConfigJob: Rolled back pending_zone_id due to job failure', [...]);
            }
        });
    } catch (\Exception $e) {
        Log::error('PublishNodeConfigJob: Error rolling back pending_zone_id', [...]);
    }
}
```

**Статус:** ✅ Исправлено

---

### ✅ ПРОБЛЕМА #2: Отсутствие проверки zone_id при завершении привязки

**Файл:** `backend/services/history-logger/main.py:1767-1777`

**Проблема:**
- При обработке `config_response` не проверялось существование зоны в БД
- Если зона была удалена между привязкой и получением `config_response`, узел всё равно переводился в `ASSIGNED_TO_ZONE`

**Исправление:**
```python
# Проверяем существование зоны
target_zone_id = zone_id or pending_zone_id
if lifecycle_state == "REGISTERED_BACKEND" and target_zone_id:
    # Проверяем существование зоны
    zone_check = await fetch(
        "SELECT id FROM zones WHERE id = $1",
        target_zone_id
    )
    if not zone_check:
        logger.warning(
            f"[CONFIG_RESPONSE] Zone {target_zone_id} not found, cannot complete binding for node {node_uid}"
        )
        CONFIG_RESPONSE_ERROR.labels(node_uid=node_uid).inc()
        return
```

**Статус:** ✅ Исправлено

---

### ✅ ПРОБЛЕМА #3: Нет retry логики для очистки retained сообщений

**Файл:** `backend/services/history-logger/main.py:1822-1842`

**Проблема:**
- Очистка retained сообщений обёрнута в `try-except`, но ошибки только логируются
- Если очистка не удалась, узел мог получить старый конфиг при переподключении

**Исправление:**
```python
# Добавляем retry логику для очистки retained сообщений
max_retries = 3
cleared = False
for attempt in range(max_retries):
    try:
        mqtt = await get_mqtt_client()
        base_client = mqtt._client
        result = base_client._client.publish(temp_topic, "", qos=1, retain=True)
        if result.rc == 0:
            logger.info(f"[CONFIG_RESPONSE] Retained message cleared on temp topic: {temp_topic}")
            cleared = True
            break
        elif attempt < max_retries - 1:
            await asyncio.sleep(0.5 * (attempt + 1))
    except Exception as clear_err:
        if attempt < max_retries - 1:
            await asyncio.sleep(0.5 * (attempt + 1))
        else:
            logger.warning(f"[CONFIG_RESPONSE] Error clearing retained message on temp topic {temp_topic} after {max_retries} attempts: {clear_err}")

if not cleared:
    logger.warning(f"[CONFIG_RESPONSE] Failed to clear retained message on temp topic {temp_topic} after {max_retries} attempts")
```

**Статус:** ✅ Исправлено

---

### ✅ Улучшено логирование в handle_config_response

**Файл:** `backend/services/history-logger/main.py:1630-1690`

**Улучшения:**
- Добавлено детальное логирование начала обработки
- Логирование извлеченного `node_uid` из топика
- Логирование payload
- Логирование состояния узла в БД
- Логирование конфига узла

**Статус:** ✅ Улучшено

---

## Тестирование

После применения исправлений рекомендуется протестировать:

1. **Тест дублирования конфига:**
   - Привязать узел к зоне
   - Проверить, что конфиг опубликован только один раз
   - Проверить логи History Logger

2. **Тест повторного node_hello:**
   - Отвязать узел от зоны
   - Отправить node_hello
   - Проверить, что состояние сброшено в REGISTERED_BACKEND

3. **Тест временного топика:**
   - Привязать узел к зоне с реальными gh_uid и zone_uid
   - Проверить, что retained сообщение очищено на правильном топике

4. **Тест отката при ошибке:**
   - Симулировать ошибку публикации конфига
   - Проверить, что pending_zone_id откатывается

5. **Тест удаления зоны:**
   - Привязать узел к зоне
   - Удалить зону
   - Отправить config_response
   - Проверить, что привязка не завершена

---

## Изменённые файлы

1. `backend/services/history-logger/main.py`
   - Исправлен хардкод временного топика
   - Добавлена проверка существования зоны
   - Добавлена retry логика для очистки retained сообщений
   - Улучшено логирование

2. `backend/laravel/app/Services/NodeService.php`
   - Убрана дублирующая публикация конфига

3. `backend/laravel/app/Services/NodeRegistryService.php`
   - Добавлен сброс состояния при повторном node_hello после отвязки

4. `backend/laravel/app/Jobs/PublishNodeConfigJob.php`
   - Добавлен откат pending_zone_id при ошибке публикации конфига

---

## Следующие шаги

1. Перезапустить History Logger для применения изменений
2. Перезапустить Laravel workers для применения изменений в Job
3. Протестировать все сценарии
4. Мониторить логи на предмет новых проблем

