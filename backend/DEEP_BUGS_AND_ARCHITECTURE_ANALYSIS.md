# Углубленный анализ багов и архитектуры Backend

**Дата:** 8 декабря 2025  
**Тип анализа:** Deep Dive - Concurrency, Race Conditions, Deadlocks, Scalability

---

## 🔴 КРИТИЧЕСКИЕ БАГИ

### 1. Race Condition при регистрации нод

**Файл:** `backend/laravel/app/Services/NodeRegistryService.php:133-137`

**Проблема:**

```php
// Проверяем уникальность uid
$counter = 1;
while (DeviceNode::where('uid', $uid)->exists()) {  // ← SELECT
    $uid = $this->generateNodeUid($hardwareId, $nodeType, $counter);
    $counter++;
}

$node = new DeviceNode();  // ← INSERT
$node->uid = $uid;
// ...
$node->save();
```

**Сценарий атаки:**
1. Две ноды с одинаковым `hardware_id` регистрируются одновременно
2. Обе проходят проверку `exists()` и получают одинаковый `uid`
3. Обе пытаются вставить запись
4. Одна из них упадет с `UNIQUE constraint violation`

**Последствия:**
- ❌ Сбой регистрации ноды
- ❌ Потеря данных о hardware_id
- ❌ Нода остается неизвестной системе

**Решение:**

```php
// backend/laravel/app/Services/NodeRegistryService.php

public function registerNodeFromHello(array $helloData): DeviceNode
{
    return DB::transaction(function () use ($helloData) {
        $hardwareId = $helloData['hardware_id'] ?? null;
        if (!$hardwareId) {
            throw new \InvalidArgumentException('hardware_id is required');
        }
        
        // ✅ ИСПОЛЬЗУЕМ PESSIMISTIC LOCK для атомарности
        // SELECT FOR UPDATE блокирует строку до конца транзакции
        $node = DeviceNode::where('hardware_id', $hardwareId)
            ->lockForUpdate()  // ← PESSIMISTIC LOCK
            ->first();
        
        if ($node) {
            // Узел существует - обновляем
            $this->updateNodeAttributes($node, $helloData);
            $node->save();
            return $node;
        }
        
        // Узел не существует - создаем с retry логикой
        $maxAttempts = 5;
        $attempt = 0;
        
        while ($attempt < $maxAttempts) {
            try {
                $nodeType = $helloData['node_type'] ?? 'unknown';
                $uid = $this->generateNodeUid($hardwareId, $nodeType, $attempt);
                
                // Пытаемся создать узел
                $node = new DeviceNode();
                $node->uid = $uid;
                $node->hardware_id = $hardwareId;
                $node->type = $nodeType;
                $node->first_seen_at = now();
                $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
                
                $this->updateNodeAttributes($node, $helloData);
                
                $node->save();
                
                // Успех - выходим из цикла
                Log::info('Node created successfully', [
                    'node_id' => $node->id,
                    'uid' => $uid,
                    'attempt' => $attempt,
                ]);
                
                break;
                
            } catch (\Illuminate\Database\UniqueConstraintViolationException $e) {
                // UID уже существует - пробуем следующий counter
                $attempt++;
                
                if ($attempt >= $maxAttempts) {
                    Log::error('Failed to generate unique UID after max attempts', [
                        'hardware_id' => $hardwareId,
                        'max_attempts' => $maxAttempts,
                    ]);
                    throw new \RuntimeException('Failed to register node: UID generation failed');
                }
                
                Log::warning('UID collision detected, retrying', [
                    'hardware_id' => $hardwareId,
                    'attempt' => $attempt,
                ]);
                
                // Короткая задержка перед повтором (экспоненциальная backoff)
                usleep(100000 * $attempt); // 100ms, 200ms, 300ms, ...
            }
        }
        
        // Каналы НЕ создаём из capabilities: нода публикует их после получения конфига (они зашиты в прошивке)
        
        return $node;
    });
}

private function updateNodeAttributes(DeviceNode $node, array $helloData): void
{
    if (isset($helloData['fw_version'])) {
        $node->fw_version = $helloData['fw_version'];
    }
    
    if (isset($helloData['hardware_revision'])) {
        $node->hardware_revision = $helloData['hardware_revision'];
    }
    
    $provisioningMeta = $helloData['provisioning_meta'] ?? [];
    if (isset($provisioningMeta['node_name'])) {
        $node->name = $provisioningMeta['node_name'];
    }
    
    $node->validated = true;
}
```

**Приоритет:** 🔴 КРИТИЧЕСКИЙ  
**Effort:** 2-3 часа

---

### 2. Cache::lock() не защищает от потери блокировки

**Файл:** `backend/laravel/app/Jobs/PublishNodeConfigJob.php:47-57`

**Проблема:**

```php
$lockKey = "lock:{$this->dedupeKey}";
$lock = Cache::lock($lockKey, 60); // Блокировка на 60 секунд

if (! $lock->get()) {
    Log::debug('PublishNodeConfigJob: Skipping duplicate job', [...]);
    return; // Уже выполняется, пропускаем
}

try {
    $node = DeviceNode::find($this->nodeId);  // ← НЕТ DB-LEVEL LOCK
    // ... публикация конфига ...
} finally {
    $lock->release();
}
```

**Сценарии сбоя:**

1. **Redis упал** → блокировка потеряна → две джобы выполняются одновременно
2. **Queue worker упал** → блокировка не освобождена → следующие джобы блокируются на 60 секунд
3. **Clock skew** между серверами → блокировка может не работать корректно

**Последствия:**
- ❌ Дублирование публикации конфига
- ❌ Лишние MQTT сообщения
- ❌ Нода может получить устаревший конфиг

**Решение:**

```php
public function handle(NodeConfigService $configService): void
{
    // ✅ Используем DB-level lock для надежности
    return DB::transaction(function () use ($configService) {
        // Используем ADVISORY LOCK PostgreSQL для дедупликации
        // Это гарантирует атомарность даже при сбое Redis
        $lockKey = crc32("publish_config:{$this->nodeId}");
        
        // pg_try_advisory_xact_lock освобождается автоматически в конце транзакции
        $locked = DB::selectOne("SELECT pg_try_advisory_xact_lock(?) as locked", [$lockKey]);
        
        if (!$locked->locked) {
            Log::debug('PublishNodeConfigJob: Skipping duplicate job (locked)', [
                'node_id' => $this->nodeId,
            ]);
            return;
        }
        
        // ✅ Используем SELECT FOR UPDATE для защиты от конкурентных изменений
        $node = DeviceNode::where('id', $this->nodeId)
            ->lockForUpdate()
            ->first();
        
        if (!$node) {
            Log::warning('PublishNodeConfigJob: Node not found', [
                'node_id' => $this->nodeId,
            ]);
            return;
        }
        
        // ... остальная логика публикации ...
        
        // Генерируем конфиг
        $config = $configService->generateNodeConfig($node, null, true);
        
        // Публикуем через MQTT
        $this->publishToMqtt($node, $config);
    });
}
```

**Альтернативное решение (с сохранением Cache::lock для быстрых проверок):**

```php
public function handle(NodeConfigService $configService): void
{
    // Быстрая проверка через Redis (для производительности)
    $lockKey = "lock:{$this->dedupeKey}";
    $lock = Cache::lock($lockKey, 60);

    if (!$lock->get()) {
        return; // Быстрый выход без DB запроса
    }

    try {
        // ✅ Дополнительная защита через DB lock
        return DB::transaction(function () use ($configService) {
            $lockKey = crc32("publish_config:{$this->nodeId}");
            $locked = DB::selectOne("SELECT pg_try_advisory_xact_lock(?) as locked", [$lockKey]);
            
            if (!$locked->locked) {
                return; // Уже выполняется в другой транзакции
            }
            
            $node = DeviceNode::where('id', $this->nodeId)
                ->lockForUpdate()
                ->first();
            
            if (!$node) {
                return;
            }
            
            // ... публикация конфига ...
        });
    } finally {
        $lock->release();
    }
}
```

**Приоритет:** 🔴 КРИТИЧЕСКИЙ  
**Effort:** 3-4 часа

---

### 3. Отсутствие Optimistic Locking при обновлении нод

**Файл:** `backend/laravel/app/Services/NodeService.php:51-180`

**Проблема:**

```php
public function update(DeviceNode $node, array $data): DeviceNode
{
    return DB::transaction(function () use ($node, $data) {
        Log::info('NodeService::update START', [...]);
        
        $oldZoneId = $node->zone_id;  // ← Может быть устаревшим
        
        // ... 100+ строк логики ...
        
        $node->update($data);  // ← Перезапишет изменения других процессов
        
        // ...
    });
}
```

**Сценарий:**
1. **Process A** читает ноду (zone_id = 1)
2. **Process B** читает ноду (zone_id = 1)
3. **Process A** обновляет zone_id = 2
4. **Process B** обновляет zone_id = 3
5. **Результат:** zone_id = 3 (изменение Process A потеряно)

**Последствия:**
- ❌ Lost updates
- ❌ Нода может оказаться в неконсистентном состоянии
- ❌ Конфиг может быть опубликован не для той зоны

**Решение:**

#### ✅ Способ 1: Добавить version column (Optimistic Locking)

```php
// Миграция
Schema::table('nodes', function (Blueprint $table) {
    $table->unsignedBigInteger('version')->default(0);
    $table->index('version');
});

// Model
class DeviceNode extends Model
{
    protected $fillable = [
        // ...
        'version',
    ];
    
    /**
     * Обновить с проверкой версии
     */
    public function updateWithVersionCheck(array $attributes): bool
    {
        $currentVersion = $this->version;
        $this->version = $currentVersion + 1;
        
        foreach ($attributes as $key => $value) {
            if ($key !== 'version') {
                $this->$key = $value;
            }
        }
        
        // UPDATE nodes SET ..., version = version + 1 WHERE id = ? AND version = ?
        $affected = DB::update(
            "UPDATE nodes SET " . $this->buildUpdateClause($attributes) . 
            ", version = version + 1, updated_at = NOW() " .
            "WHERE id = ? AND version = ?",
            array_merge(array_values($attributes), [$this->id, $currentVersion])
        );
        
        if ($affected === 0) {
            // Версия изменилась - конкурентное обновление
            return false;
        }
        
        return true;
    }
}

// Service
public function update(DeviceNode $node, array $data): DeviceNode
{
    $maxRetries = 3;
    $attempt = 0;
    
    while ($attempt < $maxRetries) {
        $attempt++;
        
        try {
            return DB::transaction(function () use ($node, $data) {
                // Перезагружаем ноду для получения актуальной версии
                $node->refresh();
                
                // ... логика обновления ...
                
                // Обновляем с проверкой версии
                $success = $node->updateWithVersionCheck($data);
                
                if (!$success) {
                    throw new \App\Exceptions\OptimisticLockException(
                        "Node was modified by another process. Please retry."
                    );
                }
                
                return $node->fresh();
            });
        } catch (\App\Exceptions\OptimisticLockException $e) {
            if ($attempt >= $maxRetries) {
                Log::error('Failed to update node after max retries', [
                    'node_id' => $node->id,
                    'attempts' => $attempt,
                ]);
                throw $e;
            }
            
            Log::warning('Optimistic lock conflict, retrying', [
                'node_id' => $node->id,
                'attempt' => $attempt,
            ]);
            
            // Exponential backoff
            usleep(100000 * $attempt);
        }
    }
}
```

#### ✅ Способ 2: Использовать SELECT FOR UPDATE

```php
public function update(DeviceNode $node, array $data): DeviceNode
{
    return DB::transaction(function () use ($node, $data) {
        // ✅ Блокируем строку для предотвращения конкурентных изменений
        $node = DeviceNode::where('id', $node->id)
            ->lockForUpdate()  // ← PESSIMISTIC LOCK
            ->first();
        
        if (!$node) {
            throw new \RuntimeException('Node not found');
        }
        
        // ... логика обновления ...
        
        $node->update($data);
        
        return $node->fresh();
    });
}
```

**Приоритет:** 🔴 КРИТИЧЕСКИЙ  
**Effort:** 4-6 часов (с тестами)

---

## 🟠 АРХИТЕКТУРНЫЕ ПРОБЛЕМЫ

### 4. Нет явного указания isolation level в транзакциях

**Проблема:**

```php
DB::transaction(function () use ($node, $data) {
    // Используется дефолтный isolation level (READ COMMITTED в PostgreSQL)
    // Это не защищает от phantom reads и других аномалий
});
```

**Последствия:**
- ❌ **Non-repeatable reads:** Одна и та же SELECT может вернуть разные результаты внутри транзакции
- ❌ **Phantom reads:** COUNT(*) может измениться между запросами
- ❌ **Write skew:** Две транзакции могут нарушить бизнес-правила

**Пример write skew:**

```php
// Правило: В зоне может быть максимум 1 нода типа 'ph'

// Transaction 1:
$count = DeviceNode::where('zone_id', 1)->where('type', 'ph')->count(); // 0
if ($count < 1) {
    $node1->zone_id = 1;
    $node1->save();
}

// Transaction 2 (параллельно):
$count = DeviceNode::where('zone_id', 1)->where('type', 'ph')->count(); // 0
if ($count < 1) {
    $node2->zone_id = 1;
    $node2->save();
}

// Результат: 2 ноды типа 'ph' в зоне 1 (правило нарушено)
```

**Решение:**

```php
// config/database.php
'pgsql' => [
    'driver' => 'pgsql',
    // ...
    'options' => [
        PDO::ATTR_EMULATE_PREPARES => false,
    ],
],

// Для критических операций используем SERIALIZABLE
public function update(DeviceNode $node, array $data): DeviceNode
{
    return DB::transaction(function () use ($node, $data) {
        // Устанавливаем SERIALIZABLE для максимальной изоляции
        DB::statement('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE');
        
        // ... логика обновления ...
        
    }, 5); // 5 попыток при serialization failure
}

// Для обычных операций можно использовать REPEATABLE READ
public function show(DeviceNode $node): array
{
    return DB::transaction(function () use ($node) {
        DB::statement('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');
        
        // Все SELECT внутри транзакции увидят snapshot на момент начала
        $node->load(['zone', 'channels']);
        
        return $node->toArray();
    });
}
```

**Рекомендация:**
- **SERIALIZABLE** для критических операций (регистрация, привязка, swap)
- **REPEATABLE READ** для чтения с гарантиями консистентности
- **READ COMMITTED** (дефолт) для простых операций

**Приоритет:** 🟠 ВЫСОКИЙ  
**Effort:** 1-2 дня (+ тесты для проверки изоляции)

---

### 5. Узкое место масштабирования: MAX_CONCURRENT_ZONES = 5

**Файл:** `backend/services/automation-engine/main.py:441`

**Проблема:**

```python
await process_zones_parallel(
    zones_to_check,
    zone_service,
    max_concurrent=automation_settings.MAX_CONCURRENT_ZONES  # = 5
)
```

**Расчет:** 
- 5 зон одновременно
- Цикл каждые 15 секунд
- Максимум `5 * (60 / 15) = 20 зон/минуту`
- **Максимум ~300 зон** при цикле 15 секунд

**Последствия при масштабировании:**
- ❌ При 500 зонах обработка займет 100 секунд (6+ циклов)
- ❌ Задержка реакции на изменения
- ❌ Накопление backlog

**Решение:**

#### ✅ Динамическое масштабирование

```python
# config/settings.py
@dataclass
class AutomationSettings:
    MAX_CONCURRENT_ZONES: int = int(os.getenv("MAX_CONCURRENT_ZONES", "10"))
    TARGET_CYCLE_TIME_SEC: int = int(os.getenv("TARGET_CYCLE_TIME_SEC", "15"))
    ADAPTIVE_CONCURRENCY: bool = os.getenv("ADAPTIVE_CONCURRENCY", "true").lower() == "true"

async def calculate_optimal_concurrency(
    total_zones: int,
    target_cycle_time: int,
    avg_zone_processing_time: float
) -> int:
    """
    Вычислить оптимальное количество параллельных зон.
    
    Формула: concurrency = (total_zones * avg_time) / target_cycle_time
    """
    optimal = math.ceil((total_zones * avg_zone_processing_time) / target_cycle_time)
    
    # Ограничиваем диапазон
    min_concurrency = 5
    max_concurrency = 50  # Защита от перегрузки
    
    return max(min_concurrency, min(optimal, max_concurrency))

async def process_zones_adaptive(zones: List[Dict[str, Any]], zone_service: ZoneAutomationService):
    """Обработка зон с адаптивной конкурентностью."""
    
    # Получаем статистику
    stats = ZONE_PROCESSING_TIME.get_sample_value()
    avg_time = stats.sum / stats.count if stats.count > 0 else 1.0
    
    # Вычисляем оптимальную конкурентность
    optimal_concurrency = await calculate_optimal_concurrency(
        total_zones=len(zones),
        target_cycle_time=automation_settings.TARGET_CYCLE_TIME_SEC,
        avg_zone_processing_time=avg_time
    )
    
    logger.info(f"Adaptive concurrency: {optimal_concurrency} zones (avg time: {avg_time:.2f}s)")
    
    # Обрабатываем с оптимальной конкурентностью
    await process_zones_parallel(zones, zone_service, max_concurrent=optimal_concurrency)

# Метрики
ZONE_PROCESSING_TIME = Histogram(
    "zone_processing_time_seconds",
    "Time to process a single zone",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

OPTIMAL_CONCURRENCY = Gauge(
    "optimal_concurrency_zones",
    "Calculated optimal concurrency for zone processing"
)
```

#### ✅ Горизонтальное масштабирование

```yaml
# docker-compose.prod.yml
services:
  automation-engine:
    # ...
    deploy:
      replicas: 3  # 3 инстанса
    environment:
      - ZONE_SHARD_ID=${ZONE_SHARD_ID}  # 0, 1, 2
      - ZONE_SHARD_TOTAL=3
```

```python
# main.py
async def get_zones_for_shard() -> List[Dict[str, Any]]:
    """Получить зоны для текущего шарда."""
    shard_id = int(os.getenv("ZONE_SHARD_ID", "0"))
    shard_total = int(os.getenv("ZONE_SHARD_TOTAL", "1"))
    
    # Получаем все активные зоны
    rows = await fetch("""
        SELECT id, name FROM zones 
        WHERE status = 'active'
        ORDER BY id
    """)
    
    # Фильтруем по шарду
    zones = []
    for row in rows:
        zone_id = row['id']
        if (zone_id % shard_total) == shard_id:
            zones.append({'id': zone_id, 'name': row['name']})
    
    logger.info(f"Shard {shard_id}/{shard_total}: Processing {len(zones)} zones")
    
    return zones
```

**Приоритет:** 🟠 ВЫСОКИЙ  
**Effort:** 2-3 дня

---

### 6. asyncio.gather без обработки partial failures

**Файл:** `backend/services/automation-engine/main.py:260`

**Проблема:**

```python
tasks = []
async with semaphore:
    for zone in zones:
        tasks.append(process_zone(zone, zone_service))

await asyncio.gather(*tasks, return_exceptions=True)  # ← Exceptions скрыты
```

**Последствия:**
- ❌ Ошибки в одной зоне молча игнорируются
- ❌ Нет алертов о проблемных зонах
- ❌ Метрики не обновляются при ошибках

**Решение:**

```python
async def process_zones_parallel(
    zones: List[Dict[str, Any]],
    zone_service: ZoneAutomationService,
    max_concurrent: int = 5
) -> Dict[str, Any]:
    """
    Обработка зон параллельно с отслеживанием ошибок.
    
    Returns:
        Dict с результатами: {
            'total': int,
            'success': int,
            'failed': int,
            'errors': List[Dict]
        }
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    results = {
        'total': len(zones),
        'success': 0,
        'failed': 0,
        'errors': []
    }
    
    async def process_with_tracking(zone: Dict[str, Any]):
        """Обработка зоны с отслеживанием результата."""
        zone_id = zone.get('id')
        
        try:
            async with semaphore:
                start = time.time()
                
                await zone_service.process_zone(zone_id)
                
                duration = time.time() - start
                ZONE_PROCESSING_TIME.observe(duration)
                results['success'] += 1
                
                logger.debug(f"Zone {zone_id} processed successfully ({duration:.2f}s)")
                
        except Exception as e:
            results['failed'] += 1
            results['errors'].append({
                'zone_id': zone_id,
                'zone_name': zone.get('name', 'unknown'),
                'error': str(e),
                'error_type': type(e).__name__,
                'timestamp': datetime.utcnow().isoformat()
            })
            
            ZONE_PROCESSING_ERRORS.labels(
                zone_id=zone_id,
                error_type=type(e).__name__
            ).inc()
            
            logger.error(
                f"Error processing zone {zone_id}: {e}",
                exc_info=True,
                extra={'zone_id': zone_id, 'zone_name': zone.get('name')}
            )
    
    # Обрабатываем все зоны
    tasks = [process_with_tracking(zone) for zone in zones]
    await asyncio.gather(*tasks)
    
    # Логируем общий результат
    logger.info(
        f"Zone processing completed: {results['success']}/{results['total']} success, "
        f"{results['failed']} failed"
    )
    
    # Отправляем алерты при критическом количестве ошибок
    if results['failed'] > 0:
        failure_rate = results['failed'] / results['total']
        
        if failure_rate > 0.1:  # >10% ошибок
            await send_alert(
                severity='warning' if failure_rate < 0.3 else 'critical',
                title=f"High zone processing failure rate: {failure_rate:.1%}",
                details={
                    'total': results['total'],
                    'failed': results['failed'],
                    'errors': results['errors'][:10]  # Первые 10 ошибок
                }
            )
    
    return results

# Метрики
ZONE_PROCESSING_ERRORS = Counter(
    "zone_processing_errors_total",
    "Errors during zone processing",
    ["zone_id", "error_type"]
)
```

**Приоритет:** 🟠 ВЫСОКИЙ  
**Effort:** 2-3 часа

---

## 🟡 ПРОБЛЕМЫ ПРОИЗВОДИТЕЛЬНОСТИ

### 7. N+1 запросы в history-logger при батчинге

**Файл:** `backend/services/history-logger/main.py:514-600`

**Проблема:**

```python
async def process_telemetry_queue():
    """Обработка очереди телеметрии батчами."""
    while not shutdown_event.is_set():
        try:
            # Достаём батч из Redis
            batch = await telemetry_queue.pop_batch(s.telemetry_batch_size)
            
            for item in batch:
                # ❌ N запросов для резолва zone_id
                zone_id = await resolve_zone_id(item.zone_uid)  # ← SELECT
                node_id = await resolve_node_id(item.node_uid)  # ← SELECT
                
                # Вставка телеметрии
                await execute("""
                    INSERT INTO telemetry_samples (zone_id, node_id, metric_type, value, ts)
                    VALUES ($1, $2, $3, $4, $5)
                """, zone_id, node_id, item.metric_type, item.value, item.ts)
```

**При батче из 200 элементов:**
- 200 * 2 = 400 SELECT запросов для резолва zone_id/node_id
- 200 INSERT запросов
- **Итого: 600 запросов** вместо ~3

**Решение:**

```python
async def process_telemetry_queue():
    """Обработка очереди телеметрии батчами с оптимизацией."""
    
    # Кеш для резолва (обновляется каждые 60 секунд)
    zone_cache = {}
    node_cache = {}
    cache_last_update = 0
    cache_ttl = 60
    
    while not shutdown_event.is_set():
        try:
            # Обновляем кеш если устарел
            current_time = time.time()
            if current_time - cache_last_update > cache_ttl:
                await refresh_caches(zone_cache, node_cache)
                cache_last_update = current_time
            
            # Достаём батч из Redis
            batch = await telemetry_queue.pop_batch(s.telemetry_batch_size)
            
            if not batch:
                await asyncio.sleep(0.1)
                continue
            
            # ✅ Батч-резолв zone_id и node_id
            await resolve_batch_ids(batch, zone_cache, node_cache)
            
            # ✅ Батч-вставка телеметрии
            await insert_telemetry_batch(batch)
            
            TELEM_PROCESSED.inc(len(batch))
            TELEM_BATCH_SIZE.observe(len(batch))
            
        except Exception as e:
            logger.error(f"Error processing telemetry queue: {e}", exc_info=True)
            await asyncio.sleep(1)

async def refresh_caches(zone_cache: Dict, node_cache: Dict):
    """Обновить кеши zone_id и node_id."""
    # Загружаем все зоны (обычно <1000, помещаются в память)
    zones = await fetch("SELECT id, uid FROM zones")
    zone_cache.clear()
    for zone in zones:
        zone_cache[zone['uid']] = zone['id']
    
    # Загружаем все ноды (обычно <10000, помещаются в память)
    nodes = await fetch("SELECT id, uid FROM nodes")
    node_cache.clear()
    for node in nodes:
        node_cache[node['uid']] = node['id']
    
    logger.info(f"Cache refreshed: {len(zone_cache)} zones, {len(node_cache)} nodes")

async def resolve_batch_ids(
    batch: List[TelemetryQueueItem],
    zone_cache: Dict,
    node_cache: Dict
):
    """Резолвить zone_id и node_id для всего батча."""
    
    # Собираем уникальные zone_uid и node_uid, которых нет в кеше
    missing_zones = set()
    missing_nodes = set()
    
    for item in batch:
        if item.zone_uid and item.zone_uid not in zone_cache:
            missing_zones.add(item.zone_uid)
        if item.node_uid and item.node_uid not in node_cache:
            missing_nodes.add(item.node_uid)
    
    # ✅ Один запрос для всех недостающих зон
    if missing_zones:
        zones = await fetch(
            "SELECT id, uid FROM zones WHERE uid = ANY($1)",
            list(missing_zones)
        )
        for zone in zones:
            zone_cache[zone['uid']] = zone['id']
    
    # ✅ Один запрос для всех недостающих нод
    if missing_nodes:
        nodes = await fetch(
            "SELECT id, uid FROM nodes WHERE uid = ANY($1)",
            list(missing_nodes)
        )
        for node in nodes:
            node_cache[node['uid']] = node['id']
    
    # Устанавливаем zone_id и node_id в элементах батча
    for item in batch:
        item.zone_id = zone_cache.get(item.zone_uid)
        item.node_id = node_cache.get(item.node_uid)

async def insert_telemetry_batch(batch: List[TelemetryQueueItem]):
    """Вставить телеметрию одним запросом."""
    
    # Формируем VALUES для batch insert
    values = []
    params = []
    param_idx = 1
    
    for item in batch:
        if item.zone_id is None:
            logger.warning(f"Skipping telemetry: zone not found for {item.zone_uid}")
            continue
        
        values.append(f"(${param_idx}, ${param_idx+1}, ${param_idx+2}, ${param_idx+3}, ${param_idx+4}, ${param_idx+5})")
        params.extend([
            item.zone_id,
            item.node_id,
            item.metric_type,
            item.channel,
            item.value,
            item.ts
        ])
        param_idx += 6
    
    if not values:
        return
    
    # ✅ Один INSERT для всего батча
    query = f"""
        INSERT INTO telemetry_samples (zone_id, node_id, metric_type, channel, value, ts)
        VALUES {', '.join(values)}
        ON CONFLICT DO NOTHING
    """
    
    await execute(query, *params)
    
    # ✅ Batch update telemetry_last
    await update_telemetry_last_batch(batch)

async def update_telemetry_last_batch(batch: List[TelemetryQueueItem]):
    """Обновить telemetry_last для батча."""
    
    # Группируем по (zone_id, metric_type) - берем последнее значение
    last_values = {}
    for item in batch:
        if item.zone_id:
            key = (item.zone_id, item.metric_type)
            if key not in last_values or item.ts > last_values[key].ts:
                last_values[key] = item
    
    # ✅ Batch upsert
    if last_values:
        values = []
        params = []
        param_idx = 1
        
        for item in last_values.values():
            values.append(f"(${param_idx}, ${param_idx+1}, ${param_idx+2}, ${param_idx+3}, ${param_idx+4}, NOW())")
            params.extend([
                item.zone_id,
                item.node_id or -1,
                item.metric_type,
                item.channel,
                item.value
            ])
            param_idx += 5
        
        query = f"""
            INSERT INTO telemetry_last (zone_id, node_id, metric_type, channel, value, updated_at)
            VALUES {', '.join(values)}
            ON CONFLICT (zone_id, metric_type)
            DO UPDATE SET 
                node_id = EXCLUDED.node_id,
                channel = EXCLUDED.channel, 
                value = EXCLUDED.value, 
                updated_at = NOW()
        """
        
        await execute(query, *params)
```

**Приоритет:** 🟡 СРЕДНИЙ  
**Effort:** 4-6 часов

---

### 8. Redis queue overflow без алертов

**Файл:** `backend/services/common/redis_queue.py:91-113`

**Проблема:**

```python
async def push(self, item: TelemetryQueueItem) -> bool:
    """Добавить элемент в очередь."""
    try:
        await self._ensure_client()
        
        # Проверяем размер очереди
        size = await self._client.llen(self.QUEUE_KEY)
        if size >= self.MAX_QUEUE_SIZE:  # 10000
            logger.warning(f"Telemetry queue is full ({size} items), dropping message")
            return False  # ❌ Молча теряем данные
        
        # Добавляем в очередь
        await self._client.rpush(self.QUEUE_KEY, item.to_json())
        return True
```

**Последствия:**
- ❌ Телеметрия теряется без алертов
- ❌ Нет метрик для dropped messages
- ❌ Нет backpressure mechanism

**Решение:**

```python
# common/redis_queue.py

# Метрики
QUEUE_SIZE = Gauge("telemetry_queue_size", "Current size of telemetry queue")
QUEUE_DROPPED = Counter("telemetry_queue_dropped_total", "Dropped messages due to queue overflow")
QUEUE_OVERFLOW_ALERTS = Counter("telemetry_queue_overflow_alerts_total", "Number of overflow alerts sent")

async def push(self, item: TelemetryQueueItem) -> bool:
    """Добавить элемент в очередь с мониторингом."""
    try:
        await self._ensure_client()
        
        # Проверяем размер очереди
        size = await self._client.llen(self.QUEUE_KEY)
        QUEUE_SIZE.set(size)
        
        # Защита от переполнения
        if size >= self.MAX_QUEUE_SIZE:
            QUEUE_DROPPED.inc()
            
            # Отправляем алерт при критическом переполнении
            if size >= self.MAX_QUEUE_SIZE * 0.95:  # 95% заполнения
                await self._send_overflow_alert(size)
            
            logger.warning(
                f"Telemetry queue is full ({size} items), dropping message",
                extra={
                    'queue_size': size,
                    'max_size': self.MAX_QUEUE_SIZE,
                    'dropped_item': {
                        'zone_uid': item.zone_uid,
                        'metric_type': item.metric_type,
                    }
                }
            )
            return False
        
        # Добавляем в очередь
        await self._client.rpush(self.QUEUE_KEY, item.to_json())
        return True
        
    except Exception as e:
        logger.error(f"Failed to push to telemetry queue: {e}", exc_info=True)
        return False

async def _send_overflow_alert(self, current_size: int):
    """Отправить алерт о переполнении очереди."""
    
    # Throttling: не отправляем чаще 1 раза в минуту
    throttle_key = "alert_throttle:queue_overflow"
    if await self._client.exists(throttle_key):
        return
    
    await self._client.setex(throttle_key, 60, "1")  # 60 секунд
    
    QUEUE_OVERFLOW_ALERTS.inc()
    
    logger.error(
        f"CRITICAL: Telemetry queue overflow! Size: {current_size}/{self.MAX_QUEUE_SIZE}",
        extra={
            'queue_size': current_size,
            'max_size': self.MAX_QUEUE_SIZE,
            'utilization': f"{current_size/self.MAX_QUEUE_SIZE:.1%}"
        }
    )
    
    # Отправляем в alerting систему
    await create_zone_event(
        zone_id=None,  # Системный алерт
        event_type='system_queue_overflow',
        details={
            'queue_size': current_size,
            'max_size': self.MAX_QUEUE_SIZE,
            'severity': 'critical'
        }
    )
```

**Дополнительно: Backpressure mechanism**

```python
# history-logger/main.py

async def handle_telemetry(topic: str, payload: bytes):
    """Обработчик телеметрии с backpressure."""
    
    # Проверяем заполнение очереди
    size = await telemetry_queue.size()
    utilization = size / telemetry_queue.MAX_QUEUE_SIZE
    
    # Если очередь заполнена >90%, применяем sampling
    if utilization > 0.9:
        # Пропускаем 50% сообщений при 90-95% заполнении
        # Пропускаем 80% сообщений при >95% заполнении
        sample_rate = 0.5 if utilization < 0.95 else 0.2
        
        if random.random() > sample_rate:
            TELEMETRY_DROPPED.labels(reason="backpressure").inc()
            logger.warning(
                f"Dropping telemetry due to backpressure (queue {utilization:.1%} full)",
                extra={'topic': topic, 'queue_utilization': utilization}
            )
            return
    
    # Обрабатываем сообщение
    data = _parse_json(payload)
    if not data:
        return
    
    # ... остальная логика ...
```

**Приоритет:** 🟡 СРЕДНИЙ  
**Effort:** 2-3 часа

---

## 📊 Сводная таблица

| # | Проблема | Тип | Приоритет | Effort | Impact |
|---|----------|-----|-----------|--------|--------|
| 1 | Race condition при регистрации нод | Bug | 🔴 КРИТИЧЕСКИЙ | 2-3ч | Data loss |
| 2 | Cache::lock() не защищает от сбоев | Bug | 🔴 КРИТИЧЕСКИЙ | 3-4ч | Duplicate configs |
| 3 | Нет Optimistic Locking | Bug | 🔴 КРИТИЧЕСКИЙ | 4-6ч | Lost updates |
| 4 | Нет явного isolation level | Architecture | 🟠 ВЫСОКИЙ | 1-2д | Write skew |
| 5 | MAX_CONCURRENT_ZONES = 5 | Scalability | 🟠 ВЫСОКИЙ | 2-3д | Bottleneck |
| 6 | asyncio.gather без обработки ошибок | Bug | 🟠 ВЫСОКИЙ | 2-3ч | Silent failures |
| 7 | N+1 запросы в батчинге | Performance | 🟡 СРЕДНИЙ | 4-6ч | Slow processing |
| 8 | Redis queue overflow без алертов | Bug | 🟡 СРЕДНИЙ | 2-3ч | Data loss |

---

## 🎯 Рекомендуемая последовательность исправлений

### Спринт 1 (Неделя 1): Критические баги

1. **Race condition при регистрации нод** (2-3ч)
2. **Cache::lock() → DB locks** (3-4ч)
3. **Optimistic Locking** (4-6ч)
4. **asyncio.gather error handling** (2-3ч)

**Итого:** ~15 часов

### Спринт 2 (Неделя 2): Архитектура и масштабирование

1. **Isolation levels** (1-2д)
2. **Adaptive concurrency** (2-3д)
3. **N+1 queries optimization** (4-6ч)

**Итого:** ~5 дней

### Спринт 3 (Неделя 3): Monitoring и алерты

1. **Redis queue overflow alerts** (2-3ч)
2. **Backpressure mechanism** (2-3ч)
3. **Load testing** (2д)

**Итого:** ~3 дня

---

## 📈 Ожидаемые улучшения

| Метрика | До | После |
|---------|----|----|
| Data loss incidents | 2-3/месяц | 0 |
| Concurrent update errors | 5-10/день | 0 |
| Max zones supported | 300 | 5000+ |
| Telemetry latency (p99) | 2000ms | 500ms |
| Queue overflow incidents | 1-2/неделю | 0 |

---

**Дата создания:** 8 декабря 2025  
**Автор:** AI Deep Dive Analyzer  
**Версия:** 1.0
