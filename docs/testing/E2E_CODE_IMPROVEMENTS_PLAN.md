# План доработки боевого кода согласно E2E тестам

## Статус E2E тестов (обновлено)

**Пройдено:** ✅ **31/31 тестов (100%)**  
**Дата проверки:** 2025-12-14  
**Все тесты проходят, но многие проверки помечены как optional из-за проблем в боевом коде**

## Анализ optional проверок

На основе анализа тестов, где проверки помечены как `optional: true`, выявлены следующие проблемы:

1. **Rate limiting** - блокирует создание алертов при частых ошибках (E20, E21, E24, E25)
2. **Automation Engine** - не всегда активен или не создает команды (E60-E63)
3. **Fault injection** - не работает в контейнере (E24, E25, E70)
4. **Alert deduplication** - может работать нестабильно (E21)
5. **DLQ механизм** - может быть неполным (E25)
6. **Unassigned node errors** - обработка может быть неполной (E22, E23)
7. **Zone readiness** - проверки отключены для E2E (E40, E41)

---

## Приоритеты доработки

### P0 - Критичные проблемы (блокируют функциональность)

#### 1. ✅ Zone Start Cycle Endpoint (`POST /api/zones/{id}/start`)
**Статус:** ✅ РЕАЛИЗОВАНО  
**Где используется:** E40, E41, E51, E54  
**Проблема:** Работает, но REQUIRED_BINDINGS отключены для E2E  
**Требуется доработка:**
- Включить REQUIRED_BINDINGS проверки в production
- Добавить конфигурацию для E2E окружения (возможность отключить strict проверки)
- Улучшить логирование readiness проверок

#### 2. ✅ Zone Readiness Service
**Статус:** ✅ РЕАЛИЗОВАНО (но отключено для E2E)  
**Где используется:** E40, E41  
**Требуется доработка:**
- Включить REQUIRED_BINDINGS проверки в production коде
- Добавить возможность настройки через конфиг (.env или config/zones.php)
- Улучшить детализацию ошибок и warnings

```php
// config/zones.php
return [
    'readiness' => [
        'required_bindings' => env('ZONE_REQUIRED_BINDINGS', ['main_pump']),
        'strict_mode' => env('ZONE_READINESS_STRICT', true),
        'e2e_mode' => env('APP_ENV') === 'e2e',
    ],
];
```

#### 3. ✅ Zone Snapshot & Events Endpoints
**Статус:** ✅ РЕАЛИЗОВАНО  
**Где используется:** E30, E31, E32, E54, E72  
**Проблема:** Работает корректно  
**Требуется доработка (опционально):**
- Оптимизация запросов для больших зон
- Добавить кэширование snapshot для зон без активных изменений

#### 4. Alert Rate Limiting
**Проблема:** Rate limiting блокирует создание алертов при частых ошибках  
**Где используется:** E20, E21, E24, E25  
**Файлы:**
- `backend/laravel/app/Services/AlertService.php`

**Требования:**
- Настроить rate limiting более гибко для критичных ошибок
- Добавить whitelist для критичных error_codes (не подвергать rate limiting)
- Улучшить дедупликацию (E21 показывает проблемы)
- Логирование rate limit событий

```php
// config/alerts.php
return [
    'rate_limiting' => [
        'enabled' => env('ALERTS_RATE_LIMIT_ENABLED', true),
        'max_per_minute' => env('ALERTS_MAX_PER_MINUTE', 10),
        'critical_codes' => [
            'infra_sensor_failure',
            'infra_pump_failure',
            'infra_controller_failure',
        ], // Эти коды не подлежат rate limiting
    ],
];
```

---

### P1 - Важные улучшения (влияют на качество)

#### 5. Automation Engine Reliability
**Проблема:** Automation Engine не всегда активен или не создает команды  
**Где используется:** E60, E61, E62, E63  
**Файлы:**
- `backend/services/automation-engine/` - основной сервис
- `backend/laravel/app/Services/AutomationEngineService.php` (если есть интеграция)

**Требования:**
- Гарантировать запуск automation-engine при старте системы
- Добавить health check для automation-engine
- Улучшить обработку stale telemetry (E61)
- Реализовать fault isolation для контроллеров (E62)
- Реализовать backoff/degraded mode при ошибках (E63)
- Логирование всех действий automation-engine

**Метрики для мониторинга:**
- Количество обработанных telemetry событий
- Количество созданных команд
- Время отклика на telemetry изменения
- Частота ошибок контроллеров

#### 6. Alert Deduplication Improvement
**Проблема:** Дедупликация может работать нестабильно  
**Где используется:** E21  
**Файлы:**
- `backend/laravel/app/Services/AlertService.php`

**Требования:**
- Улучшить логику дедупликации (проверка по error_code + node_id + zone_id)
- Обновление счетчика `error_count` должно быть атомарным
- Добавить индекс на `(code, node_id, zone_id, status)` для быстрого поиска
- Логирование событий дедупликации

```php
// Улучшенная логика дедупликации
$existingAlert = Alert::where('code', $errorCode)
    ->where('node_id', $nodeId)
    ->where('zone_id', $zoneId)
    ->where('status', 'ACTIVE')
    ->lockForUpdate() // Для атомарности
    ->first();

if ($existingAlert) {
    DB::table('alerts')
        ->where('id', $existingAlert->id)
        ->increment('error_count');
    return $existingAlert;
}
```

#### 7. Dead Letter Queue (DLQ) Mechanism
**Проблема:** DLQ механизм может быть неполным  
**Где используется:** E25  
**Файлы:**
- `backend/laravel/app/Jobs/ProcessAlert.php`
- `backend/laravel/app/Services/AlertService.php`
- `backend/laravel/database/migrations/` - таблица `pending_alerts`

**Требования:**
- Полная реализация DLQ механизма
- Retry механизм с exponential backoff
- API endpoint для replay: `POST /api/alerts/dlq/{id}/replay`
- Мониторинг размера DLQ
- Автоматический replay для старых записей (старше 24 часов)

```php
// Пример DLQ структуры
Schema::create('pending_alerts', function (Blueprint $table) {
    $table->id();
    $table->unsignedBigInteger('zone_id');
    $table->string('error_code');
    $table->json('payload_json');
    $table->integer('attempts')->default(0);
    $table->integer('max_attempts')->default(3);
    $table->timestamp('last_attempt_at')->nullable();
    $table->string('status')->default('pending'); // pending, failed, dlq
    $table->timestamps();
    
    $table->index(['status', 'created_at']);
});
```

#### 8. Unassigned Node Errors Processing
**Проблема:** Обработка ошибок от непривязанных узлов может быть неполной  
**Где используется:** E22, E23  
**Файлы:**
- `backend/laravel/app/Services/NodeRegistryService.php`
- `backend/services/history-logger/` - обработка temp-топиков

**Требования:**
- Гарантировать обработку ошибок из temp-топиков (`hydro/temp/{hardware_id}/error`)
- Улучшить архивирование ошибок при привязке узла
- Создание алертов из архивированных ошибок должно быть более надежным
- Логирование всех операций с unassigned errors

---

### P2 - Улучшения для полного покрытия и производительности

#### 9. Command Timeout Mechanism
**Проблема:** Автоматический переход в TIMEOUT может быть не реализован  
**Где используется:** E12, E70  
**Файлы:**
- `backend/laravel/app/Console/Commands/ProcessCommandTimeouts.php` (создать)

**Требования:**
- Задача запускается каждые 30 секунд (через Laravel scheduler)
- Проверка команд в статусе `SENT` старше 5 минут
- Автоматический переход в `TIMEOUT`
- Создание `zone_event` для timeout
- WebSocket уведомление
- Настраиваемый timeout через конфиг

```php
// app/Console/Commands/ProcessCommandTimeouts.php
protected $signature = 'commands:process-timeouts';

public function handle()
{
    $timeoutMinutes = config('commands.timeout_minutes', 5);
    $timeoutCommands = Command::where('status', 'SENT')
        ->where('sent_at', '<', now()->subMinutes($timeoutMinutes))
        ->get();
        
    foreach ($timeoutCommands as $command) {
        DB::transaction(function () use ($command) {
            $command->update(['status' => 'TIMEOUT']);
            
            ZoneEvent::create([
                'zone_id' => $command->zone_id,
                'type' => 'COMMAND_TIMEOUT',
                'payload_json' => [
                    'command_id' => $command->id,
                    'cmd_id' => $command->cmd_id,
                    'timeout_minutes' => $timeoutMinutes
                ]
            ]);
            
            broadcast(new CommandStatusUpdated($command));
        });
    }
    
    return 0;
}
```

#### 10. Fault Injection Infrastructure
**Проблема:** Fault injection не работает в контейнере  
**Где используется:** E24, E25, E70, E71, E72  
**Требования:**
- Реализовать endpoint для управляемого fault injection (только для тестирования)
- Добавить middleware для блокировки в production
- Альтернативно: использовать управляемые сбои через конфигурацию

```php
// Только для тестирования / staging
Route::middleware(['auth:sanctum', 'fault-injection'])->group(function () {
    Route::post('/api/system/fault-inject', [SystemController::class, 'faultInject']);
});
```

#### 11. System Health Endpoint Improvements
**Статус:** ✅ РЕАЛИЗОВАНО  
**Где используется:** E63, E71  
**Требуется доработка:**
- Добавить проверку automation-engine health
- Добавить проверку history-logger health
- Возвращать детальную информацию о состоянии компонентов

```php
public function health(): JsonResponse
{
    return response()->json([
        'status' => 'ok',
        'timestamp' => now()->toIso8601String(),
        'checks' => [
            'database' => $this->checkDatabase(),
            'redis' => $this->checkRedis(),
            'mqtt' => $this->checkMqtt(),
            'automation_engine' => $this->checkAutomationEngine(),
            'history_logger' => $this->checkHistoryLogger(),
        ],
    ]);
}
```

#### 12. WebSocket Reconnection & Snapshot Recovery
**Статус:** ✅ Работает через E31, E72  
**Требуется доработка (опционально):**
- Оптимизация snapshot для больших зон
- Добавить сжатие snapshot данных
- Улучшить инкрементальную загрузку событий

---

## План реализации (обновлено)

### Фаза 1: Критичные доработки (1-2 недели) ✅ ЗАВЕРШЕНО
1. ✅ Реализовать `POST /api/zones/{id}/start` с readiness check
2. ✅ Создать `ZoneReadinessService` с проверками
3. ✅ Исправить `snapshot()` для возврата `last_event_id`
4. ✅ Исправить `GET /api/zones/{id}/events` с поддержкой `after_id`

### Фаза 2: Улучшение надежности (2-3 недели)
5. ⚠️ Настроить Alert Rate Limiting с whitelist для критичных ошибок
6. ⚠️ Улучшить Alert Deduplication (атомарность, индексы)
7. ⚠️ Полностью реализовать DLQ механизм для алертов
8. ⚠️ Улучшить обработку Unassigned Node Errors

### Фаза 3: Automation Engine и Timeout (2-3 недели)
9. ⚠️ Гарантировать работу Automation Engine (health checks, мониторинг)
10. ⚠️ Реализовать автоматический timeout для команд
11. ⚠️ Улучшить обработку stale telemetry в Automation Engine
12. ⚠️ Реализовать fault isolation и backoff в Automation Engine

### Фаза 4: Оптимизация и мониторинг (1-2 недели)
13. ⚠️ Добавить детальные health checks для всех компонентов
14. ⚠️ Оптимизация snapshot и events endpoints
15. ⚠️ Добавить метрики и мониторинг для критичных операций

---

## Детальные требования к доработкам

### Alert Rate Limiting (P0)

**Проблема:** Тесты E20, E21, E24, E25 показывают, что rate limiting блокирует создание алертов.

**Решение:**
```php
// app/Services/AlertService.php

private function shouldRateLimit(string $errorCode, int $zoneId): bool
{
    if (!config('alerts.rate_limiting.enabled', true)) {
        return false;
    }
    
    // Критичные ошибки не подлежат rate limiting
    $criticalCodes = config('alerts.rate_limiting.critical_codes', []);
    if (in_array($errorCode, $criticalCodes)) {
        return false;
    }
    
    $maxPerMinute = config('alerts.rate_limiting.max_per_minute', 10);
    $count = Alert::where('zone_id', $zoneId)
        ->where('created_at', '>', now()->subMinute())
        ->count();
        
    return $count >= $maxPerMinute;
}
```

### Alert Deduplication (P1)

**Проблема:** E21 показывает проблемы с дедупликацией.

**Решение:**
```php
// app/Services/AlertService.php

public function createOrUpdateAlert(array $alertData): Alert
{
    return DB::transaction(function () use ($alertData) {
        $alert = Alert::where('code', $alertData['code'])
            ->where('node_id', $alertData['node_id'])
            ->where('zone_id', $alertData['zone_id'])
            ->where('status', 'ACTIVE')
            ->lockForUpdate()
            ->first();
            
        if ($alert) {
            // Атомарное обновление счетчика
            DB::table('alerts')
                ->where('id', $alert->id)
                ->increment('error_count');
            
            // Обновляем updated_at
            $alert->touch();
            
            return $alert->fresh();
        }
        
        return Alert::create($alertData);
    });
}
```

### DLQ Mechanism (P1)

**Требования:**
- Таблица `pending_alerts` должна существовать
- При ошибке доставки алерта → сохранение в `pending_alerts`
- Retry механизм (max 3 попытки с exponential backoff)
- При превышении max_attempts → перемещение в DLQ
- API endpoint для replay: `POST /api/alerts/dlq/{id}/replay`
- Задача для автоматического replay старых записей

### Command Timeout (P2)

**Требования:**
- Laravel scheduled task: `commands:process-timeouts` каждые 30 секунд
- Проверка команд в статусе `SENT` старше N минут (настраиваемо)
- Автоматический переход в `TIMEOUT`
- Создание `zone_event` для timeout
- WebSocket уведомление
- Логирование всех timeout событий

---

## Метрики успеха

После реализации всех фаз:
- ✅ Все E2E тесты проходят (31/31) - **ДОСТИГНУТО**
- ⚠️ Стабильность 10/10 прогонов для CORE набора - **ТРЕБУЕТ ПРОВЕРКИ**
- ⚠️ Rate limiting не блокирует критичные ошибки - **ТРЕБУЕТ ДОРАБОТКИ**
- ⚠️ Automation Engine создает команды стабильно - **ТРЕБУЕТ ДОРАБОТКИ**
- ⚠️ DLQ механизм работает корректно - **ТРЕБУЕТ ДОРАБОТКИ**
- ⚠️ Alert deduplication работает атомарно - **ТРЕБУЕТ ДОРАБОТКИ**

---

## Следующие шаги

1. **Создать issues в трекере задач** для пунктов P0 и P1
2. **Начать с Фазы 2** - улучшение надежности (rate limiting, deduplication, DLQ)
3. **После каждой реализации** - запускать соответствующие E2E тесты и убирать `optional: true`
4. **Обновить конфигурацию** для production vs E2E режимов
5. **Добавить мониторинг** для всех критичных компонентов

---

## Приоритетный список задач

### Неделя 1-2: Alert System Improvements
- [ ] Настроить Alert Rate Limiting с whitelist (P0)
- [ ] Улучшить Alert Deduplication с атомарностью (P1)
- [ ] Реализовать полный DLQ механизм (P1)

### Неделя 3-4: Automation Engine
- [ ] Гарантировать работу Automation Engine (health checks) (P1)
- [ ] Улучшить обработку stale telemetry (P1)
- [ ] Реализовать fault isolation и backoff (P1)

### Неделя 5-6: Infrastructure
- [ ] Реализовать автоматический timeout для команд (P2)
- [ ] Улучшить обработку Unassigned Node Errors (P1)
- [ ] Добавить детальные health checks (P2)

---

**Последнее обновление:** 2025-12-14  
**Статус:** 31/31 тестов проходят, но требуются доработки для стабильности в production
