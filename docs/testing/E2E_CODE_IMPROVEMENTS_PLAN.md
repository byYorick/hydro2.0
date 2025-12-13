# План доработки боевого кода согласно E2E тестам

## Статус E2E тестов

**Пройдено:** ~28/31 тестов  
**Требуют доработки кода:** ~10-12 тестов имеют проблемы с API/бизнес-логикой

## Приоритеты доработки

### P0 - Критичные проблемы (блокируют функциональность)

#### 1. Zone Start Cycle Endpoint (`POST /api/zones/{id}/start`)
**Проблема:** Возвращает 500 Internal Server Error  
**Где используется:** E40, E41, E51, E54  
**Файлы:**
- `backend/laravel/routes/api.php` - добавить маршрут
- `backend/laravel/app/Http/Controllers/ZoneController.php` - реализовать метод `start()`

**Требования:**
- Проверка readiness зоны (наличие bindings, online nodes)
- Создание `zone_recipe_instance` если рецепт привязан
- Обновление статуса зоны на `RUNNING`
- Валидация: возвращать 422 с деталями если зона не готова
- Логирование событий в `zone_events`

**Пример реализации:**
```php
public function start(Request $request, Zone $zone): JsonResponse
{
    // Readiness check
    $readiness = $this->checkZoneReadiness($zone);
    if (!$readiness['ready']) {
        return response()->json([
            'status' => 'error',
            'message' => 'Zone is not ready',
            'warnings' => $readiness['warnings'],
            'errors' => $readiness['errors']
        ], 422);
    }
    
    // Start cycle logic
    // ...
}
```

#### 2. Zone Readiness Check (Readiness Service)
**Проблема:** Проверка готовности зоны не реализована  
**Где используется:** E40, E41  
**Файлы:**
- `backend/laravel/app/Services/ZoneReadinessService.php` (создать)

**Требования:**
- Проверка наличия required bindings
- Проверка online статуса узлов
- Возврат warnings для missing nodes (но start все равно работает)
- Возврат errors для missing required bindings (start блокируется)

#### 3. Zone Snapshot Endpoint (`GET /api/zones/{id}` vs `/api/zones/{id}/snapshot`)
**Проблема:** 
- `/api/zones/{id}` возвращает 500 в некоторых случаях
- `/api/zones/{id}/snapshot` не содержит `last_event_id` в ожидаемой структуре

**Где используется:** E30, E31, E54, E72  
**Файлы:**
- `backend/laravel/app/Http/Controllers/ZoneController.php` - метод `snapshot()`
- `backend/laravel/app/Http/Controllers/ZoneController.php` - метод `show()`

**Требования:**
- `snapshot()` должен гарантированно возвращать `last_event_id`
- Структура ответа должна быть консистентной:
```json
{
  "status": "ok",
  "data": {
    "last_event_id": 12345,
    "server_ts": 1234567890,
    "snapshot_id": "uuid",
    "telemetry": {...},
    "alerts": [...],
    "commands": [...]
  }
}
```

#### 4. Events Replay Endpoint (`GET /api/zones/{id}/events`)
**Проблема:** Может не возвращать корректную структуру или не обрабатывать `after_id`  
**Где используется:** E31, E32  
**Файлы:**
- `backend/laravel/app/Http/Controllers/ZoneController.php` - метод `events()`

**Требования:**
- Поддержка `after_id` параметра для инкрементальной загрузки
- Фильтрация событий: `WHERE zone_id = ? AND id > after_id`
- Ограничение лимита (по умолчанию 50, максимум 200)
- Возврат структуры: `{ "data": [...], "has_more": true/false }`

---

### P1 - Важные улучшения (влияют на качество)

#### 5. Advance Stage Endpoint (`POST /api/zones/{id}/next-phase`)
**Проблема:** Возвращает 422 или не реализован  
**Где используется:** E53  
**Файлы:**
- `backend/laravel/app/Http/Controllers/ZoneController.php` - метод `advanceStage()`

**Требования:**
- Проверка наличия активного `zone_recipe_instance`
- Проверка что текущая фаза не последняя
- Инкремент `current_phase_index`
- Создание `zone_event` для изменения фазы
- Отправка WebSocket события `ZonePhaseAdvanced`

#### 6. Zone Bindings API
**Проблема:** Таблица `zone_bindings` может отсутствовать или API не реализован  
**Где используется:** E40, E42  
**Файлы:**
- `backend/laravel/database/migrations/` - миграция для `zone_bindings`
- `backend/laravel/app/Http/Controllers/ZoneBindingController.php` (создать)

**Требования:**
- Таблица: `zone_id`, `role`, `node_id`, `channel`
- API endpoints: `POST /api/zones/{id}/bindings`, `DELETE /api/zones/{id}/bindings/{role}`
- Использование bindings при отправке команд для определения правильного MQTT топика

#### 7. Zone Status Transitions (Pause/Resume/Harvest)
**Проблема:** Endpoints могут быть неполностью реализованы  
**Где используется:** E54  
**Файлы:**
- `backend/laravel/app/Http/Controllers/ZoneController.php` - методы `pause()`, `resume()`, `harvest()`

**Требования:**
- Валидация переходов статусов (RUNNING → PAUSED → RUNNING → HARVESTED)
- Создание `zone_events` для каждого перехода
- WebSocket уведомления
- При HARVESTED - закрытие активного `zone_recipe_instance`

#### 8. System Health Endpoint (`GET /api/system/health`)
**Проблема:** Может отсутствовать или возвращать неожиданную структуру  
**Где используется:** E63, E71  
**Файлы:**
- `backend/laravel/app/Http/Controllers/SystemController.php` (создать)

**Требования:**
- Проверка доступности БД
- Проверка доступности Redis
- Проверка доступности MQTT (опционально)
- Возврат: `{ "status": "ok", "checks": {...} }`

---

### P2 - Улучшения для полного покрытия тестами

#### 9. Dead Letter Queue (DLQ) и Pending Alerts
**Проблема:** Механизм DLQ может быть не реализован  
**Где используется:** E25  
**Файлы:**
- `backend/laravel/app/Jobs/ProcessAlert.php` - обработка с retry логикой
- `backend/laravel/app/Services/AlertService.php` - интеграция с DLQ

**Требования:**
- При ошибке доставки алерта → сохранение в `pending_alerts`
- Retry механизм (max 3 попытки)
- При превышении max_attempts → перемещение в DLQ
- API endpoint для replay: `POST /api/alerts/dlq/{id}/replay`

#### 10. Automation Engine Integration
**Проблема:** Может отсутствовать интеграция или не обрабатывать события  
**Где используется:** E60, E61, E62, E63  
**Файлы:**
- `backend/services/automation-engine/` - проверка обработки telemetry
- `backend/laravel/app/Services/AutomationEngineService.php` (если есть)

**Требования:**
- Подписка на telemetry updates
- Обработка целевых значений из активной фазы рецепта
- Генерация команд для коррекции (fan, vent, heater, dosing)
- Fail-closed логика при stale telemetry
- Fault isolation для контроллеров
- Backoff/degraded mode при ошибках

#### 11. Unassigned Node Errors Archive
**Проблема:** Архив может не работать корректно  
**Где используется:** E23  
**Файлы:**
- `backend/laravel/app/Services/NodeRegistryService.php` - метод `attachUnassignedNode()`

**Требования:**
- При привязке узла → архивирование ошибок из `unassigned_node_errors` в `unassigned_node_errors_archive`
- Создание алерта из архивированных ошибок
- Очистка `unassigned_node_errors` после успешного архивирования

#### 12. Command Timeout Mechanism
**Проблема:** Автоматический переход в TIMEOUT может быть не реализован  
**Где используется:** E12, E70  
**Файлы:**
- `backend/laravel/app/Console/Commands/ProcessCommandTimeouts.php` (создать)
- `backend/laravel/app/Providers/EventServiceProvider.php` - планировщик

**Требования:**
- Задача запускается каждые 30 секунд
- Проверка команд в статусе `SENT` старше N минут (например, 5 минут)
- Автоматический переход в `TIMEOUT`
- Создание `zone_event` для timeout
- WebSocket уведомление

---

## План реализации (по приоритетам)

### Фаза 1: Критичные API endpoints (1-2 недели)
1. ✅ Реализовать `POST /api/zones/{id}/start` с readiness check
2. ✅ Создать `ZoneReadinessService` с проверками
3. ✅ Исправить `snapshot()` для возврата `last_event_id`
4. ✅ Исправить `GET /api/zones/{id}/events` с поддержкой `after_id`

### Фаза 2: Важные улучшения (2-3 недели)
5. ✅ Реализовать `POST /api/zones/{id}/next-phase`
6. ✅ Создать миграцию и API для `zone_bindings`
7. ✅ Реализовать `pause()`, `resume()`, `harvest()` методы
8. ✅ Создать `GET /api/system/health` endpoint

### Фаза 3: Полное покрытие (3-4 недели)
9. ✅ Реализовать DLQ механизм для алертов
10. ✅ Интегрировать Automation Engine (если отдельный сервис)
11. ✅ Улучшить архив unassigned errors
12. ✅ Реализовать автоматический timeout для команд

---

## Технические детали

### Zone Readiness Service

```php
namespace App\Services;

class ZoneReadinessService
{
    public function checkZoneReadiness(Zone $zone): array
    {
        $warnings = [];
        $errors = [];
        
        // Check required bindings
        $requiredBindings = ['main_pump', 'ph_control', 'ec_control'];
        $existingBindings = $zone->bindings()->pluck('role')->toArray();
        $missingBindings = array_diff($requiredBindings, $existingBindings);
        
        if (!empty($missingBindings)) {
            $errors[] = [
                'type' => 'missing_bindings',
                'message' => 'Required bindings are missing: ' . implode(', ', $missingBindings),
                'bindings' => $missingBindings
            ];
        }
        
        // Check online nodes (warning only)
        $offlineNodes = $zone->nodes()->where('status', '!=', 'ONLINE')->count();
        if ($offlineNodes > 0) {
            $warnings[] = [
                'type' => 'offline_nodes',
                'message' => "$offlineNodes node(s) are offline",
                'count' => $offlineNodes
            ];
        }
        
        return [
            'ready' => empty($errors),
            'warnings' => $warnings,
            'errors' => $errors
        ];
    }
}
```

### Command Timeout Job

```php
namespace App\Console\Commands;

class ProcessCommandTimeouts extends Command
{
    protected $signature = 'commands:process-timeouts';
    
    public function handle()
    {
        $timeoutMinutes = 5;
        $timeoutCommands = Command::where('status', 'SENT')
            ->where('sent_at', '<', now()->subMinutes($timeoutMinutes))
            ->get();
            
        foreach ($timeoutCommands as $command) {
            $command->update(['status' => 'TIMEOUT']);
            
            // Create zone event
            ZoneEvent::create([
                'zone_id' => $command->zone_id,
                'kind' => 'WARNING',
                'message' => "Command {$command->cmd_id} timed out",
                'payload_json' => ['command_id' => $command->id, 'cmd_id' => $command->cmd_id]
            ]);
            
            // WebSocket notification
            broadcast(new CommandStatusUpdated($command));
        }
        
        return 0;
    }
}
```

---

## Метрики успеха

После реализации всех фаз:
- ✅ Все E2E тесты проходят (31/31)
- ✅ Стабильность 10/10 прогонов для CORE набора
- ✅ API endpoints возвращают корректные HTTP статусы
- ✅ WebSocket события отправляются консистентно
- ✅ Database транзакции атомарны

---

## Следующие шаги

1. **Создать issues в трекере задач** для каждого пункта P0
2. **Начать с Фазы 1** - критичные endpoints
3. **После каждой реализации** - запускать соответствующие E2E тесты
4. **Обновить документацию** API после изменений

