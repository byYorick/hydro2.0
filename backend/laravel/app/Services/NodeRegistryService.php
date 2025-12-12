<?php

namespace App\Services;

use App\Enums\NodeLifecycleState;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\Zone;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class NodeRegistryService
{
    /**
     * Зарегистрировать узел в системе.
     * 
     * Если узел уже существует, обновляет его атрибуты.
     * Если узел новый, создаёт его и отмечает как validated.
     * 
     * ВАЖНО: Автопривязка к зоне отключена. Привязка должна происходить только
     * через явное действие пользователя (кнопка "Привязать" в UI).
     * 
     * @param string $nodeUid Уникальный идентификатор узла (MAC/UID)
     * @param string|null $zoneUid UID зоны (игнорируется, оставлен для обратной совместимости)
     * @param array $attributes Дополнительные атрибуты (firmware_version, hardware_revision и т.д.)
     * @return DeviceNode
     */
    public function registerNode(
        string $nodeUid,
        ?string $zoneUid = null,
        array $attributes = []
    ): DeviceNode {
        return DB::transaction(function () use ($nodeUid, $zoneUid, $attributes) {
            // Находим или создаём узел
            $node = DeviceNode::firstOrNew(['uid' => $nodeUid]);
            
            // КРИТИЧНО: Автопривязка к зоне при регистрации УДАЛЕНА
            // Привязка должна происходить только после явного действия пользователя (нажатие кнопки "Привязать")
            // Если указан zoneUid, игнорируем его и логируем предупреждение
            if ($zoneUid) {
                Log::warning('Node registration: zoneUid provided but auto-binding is disabled. Node will remain unbound until user manually attaches it.', [
                    'node_uid' => $nodeUid,
                    'requested_zone_uid' => $zoneUid,
                    'ip' => request()->ip(),
                ]);
            }
            
            // Обновляем атрибуты
            if (isset($attributes['firmware_version'])) {
                $node->fw_version = $attributes['firmware_version'];
            }
            
            if (isset($attributes['hardware_revision'])) {
                $node->hardware_revision = $attributes['hardware_revision'];
            }
            
            if (isset($attributes['name'])) {
                $node->name = $attributes['name'];
            }
            
            if (isset($attributes['type'])) {
                $node->type = $attributes['type'];
            }
            
            // Обновляем hardware_id, если указан
            if (isset($attributes['hardware_id'])) {
                $node->hardware_id = $attributes['hardware_id'];
            }
            
            // Устанавливаем first_seen_at при первом появлении
            // Проверяем через id, так как firstOrNew создаёт модель, но не сохраняет её
            if (!$node->id || !$node->first_seen_at) {
                $node->first_seen_at = now();
            }
            
            // Отмечаем как validated
            $node->validated = true;
            
            // Устанавливаем lifecycle_state в REGISTERED_BACKEND при регистрации
            if (!$node->id || !$node->lifecycle_state) {
                $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
            }
            
            $node->save();
            
            Log::info('Node registered', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'zone_id' => $node->zone_id,
                'validated' => $node->validated,
                'lifecycle_state' => $node->lifecycle_state?->value,
            ]);
            
            return $node;
        });
    }
    
    /**
     * Зарегистрировать узел из node_hello сообщения (MQTT).
     * 
     * ВАЖНО: Автопривязка к зоне отключена. Даже если в provisioning_meta указаны
     * greenhouse_token и zone_id, они игнорируются. Привязка должна происходить только
     * через явное действие пользователя (кнопка "Привязать" в UI).
     * 
     * @param array $helloData Данные из node_hello:
     *   - hardware_id: string
     *   - node_type: string
     *   - fw_version: string|null
     *   - hardware_revision: string|null
     *   - capabilities: array (используются только как метаданные, каналы по ним не создаются)
     *   - provisioning_meta: array {greenhouse_token (игнорируется), zone_id (игнорируется), node_name}
     * @return DeviceNode
     */
    public function registerNodeFromHello(array $helloData): DeviceNode
    {
        $maxRetries = 5;
        $attempt = 0;
        
        while ($attempt < $maxRetries) {
            try {
                // Устанавливаем SERIALIZABLE isolation level ДО начала транзакции
                // PostgreSQL не позволяет устанавливать isolation level внутри подтранзакции
                DB::statement('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE');
                
                return DB::transaction(function () use ($helloData) {
                    
                    $hardwareId = $helloData['hardware_id'] ?? null;
                    if (!$hardwareId) {
                        throw new \InvalidArgumentException('hardware_id is required');
                    }
                    
                    // Ищем узел по hardware_id с блокировкой для атомарности
                    $node = DeviceNode::where('hardware_id', $hardwareId)
                        ->lockForUpdate()
                        ->first();
                    
                    // Если узел не найден, создаём новый с retry логикой при UID коллизии
                    if (!$node) {
                        $nodeType = $helloData['node_type'] ?? 'unknown';
                        $maxAttempts = 5;
                        $uidAttempt = 0;
                        
                        while ($uidAttempt < $maxAttempts) {
                            try {
                                $uid = $this->generateNodeUid($hardwareId, $nodeType, $uidAttempt);
                                
                                $node = new DeviceNode();
                                $node->uid = $uid;
                                $node->hardware_id = $hardwareId;
                                $node->type = $nodeType;
                                $node->first_seen_at = now();
                                // Новые ноды с временными конфигами регистрируются как REGISTERED_BACKEND
                                // Когда нода получит реальные конфиги и будет привязана к зоне, состояние изменится на ASSIGNED_TO_ZONE
                                $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
                                
                                $node->save();
                                
                                // Успех - выходим из цикла
                                Log::info('Node created successfully', [
                                    'node_id' => $node->id,
                                    'uid' => $uid,
                                    'hardware_id' => $hardwareId,
                                    'attempt' => $uidAttempt,
                                ]);
                                
                                break;
                                
                            } catch (\Illuminate\Database\QueryException $e) {
                                // Проверяем, является ли это ошибкой уникального ограничения
                                if ($e->getCode() === '23505' || str_contains($e->getMessage(), 'duplicate key value')) {
                                    $uidAttempt++;
                                    
                                    if ($uidAttempt >= $maxAttempts) {
                                        Log::error('Failed to generate unique UID after max attempts', [
                                            'hardware_id' => $hardwareId,
                                            'max_attempts' => $maxAttempts,
                                        ]);
                                        throw new \RuntimeException('Failed to register node: UID generation failed after ' . $maxAttempts . ' attempts');
                                    }
                                    
                                    Log::warning('UID collision detected, retrying', [
                                        'hardware_id' => $hardwareId,
                                        'attempt' => $uidAttempt,
                                        'uid' => $uid ?? 'unknown',
                                    ]);
                                    
                                    // Exponential backoff: 100ms, 200ms, 300ms, ...
                                    usleep(100000 * $uidAttempt);
                                } else {
                                    // Другая ошибка - пробрасываем дальше
                                    throw $e;
                                }
                            }
                        }
                    }
                    
                    // Обновляем атрибуты
                    $this->updateNodeAttributes($node, $helloData);
                    
                    // КРИТИЧНО: Автопривязка к зоне через greenhouse_token УДАЛЕНА
                    // Привязка должна происходить только после явного действия пользователя (нажатие кнопки "Привязать")
                    // Если указан greenhouse_token или zone_id, игнорируем их и логируем предупреждение
                    $provisioningMeta = $helloData['provisioning_meta'] ?? [];
                    if (isset($provisioningMeta['greenhouse_token']) || isset($provisioningMeta['zone_id'])) {
                        Log::info('Node registration: provisioning_meta contains greenhouse_token or zone_id, but auto-binding is disabled. Node will remain unbound until user manually attaches it.', [
                            'node_id' => $node->id,
                            'hardware_id' => $hardwareId,
                            'has_greenhouse_token' => isset($provisioningMeta['greenhouse_token']),
                            'has_zone_id' => isset($provisioningMeta['zone_id']),
                            'zone_id' => $provisioningMeta['zone_id'] ?? null,
                        ]);
                    }
                    
                    // БАГ #3 FIX: Сбрасываем состояние при повторном node_hello после отвязки
                    // Если узел отвязан (zone_id = null), сбрасываем состояние в REGISTERED_BACKEND
                    if (!$node->zone_id && !$node->pending_zone_id) {
                        // Узел отвязан - сбрасываем в REGISTERED_BACKEND
                        $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
                        Log::info('NodeRegistryService: Reset lifecycle_state to REGISTERED_BACKEND for unbound node', [
                            'node_id' => $node->id,
                            'uid' => $node->uid,
                            'hardware_id' => $hardwareId,
                        ]);
                    } elseif (!$node->lifecycle_state) {
                        // Новый узел - всегда REGISTERED_BACKEND
                        $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
                    }
                    // Для существующих привязанных узлов не меняем состояние
                    // Переход в ASSIGNED_TO_ZONE произойдет только после успешной публикации конфига
                    
                    // Отмечаем как validated
                    $node->validated = true;
                    
                    $node->save();
                    
                    // Привязываем накопленные ошибки по hardware_id
                    $this->attachUnassignedErrors($node);
                    
                    // Очищаем кеш списка устройств и статистики для всех пользователей
                    // Вместо Cache::flush() используем более безопасную очистку только связанных ключей
                    // Это предотвращает DoS через частые node_hello запросы
                    // Очищаем только кеш, связанный с устройствами
                    $cachePrefixes = ['devices_list_', 'nodes_list_', 'node_stats_'];
                    foreach ($cachePrefixes as $prefix) {
                        // Laravel Cache не поддерживает поиск по префиксу напрямую
                        // Используем tags, если они доступны, или ограничиваем очистку
                        // В production лучше использовать Redis с поддержкой SCAN
                        if (config('cache.default') === 'redis') {
                            // Для Redis можно использовать более точную очистку через tags
                            // Но пока просто не очищаем весь кеш - это безопаснее
                            // Кеш устареет естественным образом через TTL
                            Log::debug('NodeRegistryService: Skipping cache flush for security', [
                                'node_id' => $node->id,
                                'cache_driver' => config('cache.default'),
                            ]);
                        } else {
                            // Для других драйверов кеша не очищаем глобально
                            // Кеш устареет естественным образом
                            Log::debug('NodeRegistryService: Skipping cache flush for security', [
                                'node_id' => $node->id,
                                'cache_driver' => config('cache.default'),
                            ]);
                        }
                    }
                    
                    Log::info('Node registered from node_hello', [
                        'node_id' => $node->id,
                        'uid' => $node->uid,
                        'hardware_id' => $hardwareId,
                        'zone_id' => $node->zone_id,
                        'lifecycle_state' => $node->lifecycle_state?->value,
                        'channels_count' => $node->channels()->count(),
                    ]);
                    
                    return $node;
                }, 5); // 5 попыток при serialization failure
            } catch (\Illuminate\Database\QueryException $e) {
                // Проверяем, является ли это serialization failure
                if ($e->getCode() === '40001' || str_contains($e->getMessage(), 'serialization failure')) {
                    $attempt++;
                    
                    if ($attempt >= $maxRetries) {
                        Log::error('Failed to register node after max retries due to serialization failure', [
                            'hardware_id' => $helloData['hardware_id'] ?? 'unknown',
                            'max_retries' => $maxRetries,
                        ]);
                        throw new \RuntimeException('Failed to register node: serialization failure after ' . $maxRetries . ' attempts');
                    }
                    
                    Log::warning('Serialization failure detected, retrying transaction', [
                        'hardware_id' => $helloData['hardware_id'] ?? 'unknown',
                        'attempt' => $attempt,
                    ]);
                    
                    // Exponential backoff: 50ms, 100ms, 150ms, ...
                    usleep(50000 * $attempt);
                } else {
                    // Другая ошибка - пробрасываем дальше
                    throw $e;
                }
            }
        }
        
        throw new \RuntimeException('Failed to register node: max retries exceeded');
    }
    
    /**
     * Обновить атрибуты узла из helloData.
     */
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
    }
    
    /**
     * Генерировать uid для узла на основе hardware_id и типа.
     * 
     * @param string $hardwareId
     * @param string $nodeType
     * @param int $counter Для уникальности, если uid уже существует
     * @return string
     */
     private function generateNodeUid(string $hardwareId, string $nodeType, int $counter = 0): string
    {
        // Используем первые 8 символов hardware_id и тип узла
        $shortId = substr(str_replace([':', '-', '_'], '', $hardwareId), 0, 8);
        
        // Определяем префикс типа узла
        $typePrefix = 'node';
        if ($nodeType === 'ph') {
            $typePrefix = 'ph';
        } elseif ($nodeType === 'ec') {
            $typePrefix = 'ec';
        } elseif ($nodeType === 'climate') {
            $typePrefix = 'clim';
        } elseif (in_array($nodeType, ['irrig', 'pump'])) {
            $typePrefix = 'irr';
        } elseif ($nodeType === 'light') {
            $typePrefix = 'light';
        }
        
        $uid = "nd-{$typePrefix}-{$shortId}";
        if ($counter > 0) {
            $uid .= "-{$counter}";
        }
        
        return $uid;
    }
    
    /**
     * Найти теплицу по токену.
     * 
     * @param string $token Greenhouse provisioning_token (секретный токен, не uid!)
     * @return Greenhouse|null
     */
    private function findGreenhouseByToken(string $token): ?Greenhouse
    {
        // Ищем по provisioning_token (секретный токен, не публичный uid)
        // Это предотвращает регистрацию нод в чужие теплицы, т.к. uid доступен всем viewer'ам
        return Greenhouse::where('provisioning_token', $token)->first();
    }
    
    /**
     * Разрешить zone_uid в zone_id.
     * 
     * @param string $zoneUid Может быть в формате "zn-1" или просто "1"
     * @return int|null
     */
    private function resolveZoneId(string $zoneUid): ?int
    {
        // Если формат zn-{id}
        if (str_starts_with($zoneUid, 'zn-')) {
            $zoneIdStr = substr($zoneUid, 3);
            if (is_numeric($zoneIdStr)) {
                // Проверяем, существует ли зона
                $zone = Zone::find((int)$zoneIdStr);
                return $zone?->id;
            }
        }
        
        // Если это просто число
        if (is_numeric($zoneUid)) {
            $zone = Zone::find((int)$zoneUid);
            return $zone?->id;
        }
        
        // В будущем можно добавить поиск по uid, если он появится в таблице zones
        return null;
    }
    
    /**
     * Привязать накопленные ошибки неназначенного узла к зарегистрированному узлу.
     * 
     * После успешного attach:
     * - Создает alerts для каждой ошибки
     * - Архивирует записи в unassigned_node_errors_archive
     * - Создает zone_event для прозрачности
     * 
     * @param DeviceNode $node Зарегистрированный узел
     */
    protected function attachUnassignedErrors(DeviceNode $node): void
    {
        if (!$node->hardware_id) {
            return;
        }
        
        try {
            // Получаем все непривязанные ошибки для этого hardware_id
            $errors = DB::table('unassigned_node_errors')
                ->where('hardware_id', $node->hardware_id)
                ->whereNull('node_id')
                ->get();
            
            if ($errors->isEmpty()) {
                return;
            }
            
            $alertsCreated = 0;
            
            // Если у ноды есть zone_id, создаем alerts для ошибок
            if ($node->zone_id) {
                $alertService = app(\App\Services\AlertService::class);
                
                foreach ($errors as $error) {
                    // Определяем source и code для алерта
                    // Используем infra_node_error как базовый код, добавляем error_code если есть
                    $alertCode = 'infra_node_error';
                    if ($error->error_code) {
                        $alertCode = 'infra_node_error_' . str_replace('-', '_', $error->error_code);
                    }
                    
                    // Преобразуем даты из строк в ISO8601 формат если нужно
                    $firstSeenAt = $error->first_seen_at;
                    if (is_string($firstSeenAt)) {
                        $firstSeenAt = \Carbon\Carbon::parse($firstSeenAt)->toIso8601String();
                    } elseif ($firstSeenAt instanceof \Carbon\Carbon || $firstSeenAt instanceof \DateTime) {
                        $firstSeenAt = $firstSeenAt->toIso8601String();
                    }
                    
                    $lastSeenAt = $error->last_seen_at;
                    if (is_string($lastSeenAt)) {
                        $lastSeenAt = \Carbon\Carbon::parse($lastSeenAt)->toIso8601String();
                    } elseif ($lastSeenAt instanceof \Carbon\Carbon || $lastSeenAt instanceof \DateTime) {
                        $lastSeenAt = $lastSeenAt->toIso8601String();
                    }
                    
                    // Создаем или обновляем алерт с сохранением count, first_seen_at, last_seen_at
                    // Проверяем, существует ли уже активный алерт с таким code
                    $existingAlert = \App\Models\Alert::where('zone_id', $node->zone_id)
                        ->where('code', $alertCode)
                        ->where('status', 'ACTIVE')
                        ->first();
                    
                    if ($existingAlert) {
                        // Обновляем существующий алерт, сохраняя максимальный count и earliest first_seen_at
                        $existingDetails = $existingAlert->details ?? [];
                        $existingCount = $existingDetails['count'] ?? 0;
                        $newCount = max($existingCount, $error->count ?? 1);
                        
                        // Сохраняем earliest first_seen_at
                        $existingFirstSeenAt = $existingDetails['first_seen_at'] ?? null;
                        if ($existingFirstSeenAt && $firstSeenAt) {
                            try {
                                $existingFirstSeen = \Carbon\Carbon::parse($existingFirstSeenAt);
                                $newFirstSeen = \Carbon\Carbon::parse($firstSeenAt);
                                if ($newFirstSeen->lt($existingFirstSeen)) {
                                    $firstSeenAt = $newFirstSeen->toIso8601String();
                                } else {
                                    $firstSeenAt = $existingFirstSeenAt;
                                }
                            } catch (\Exception $e) {
                                // Если не удалось распарсить, используем новый
                            }
                        }
                        
                        $alertService->createOrUpdateActive([
                            'zone_id' => $node->zone_id,
                            'source' => 'infra',
                            'code' => $alertCode,
                            'type' => 'Node Error: ' . ($error->error_message ?: 'Unknown error'),
                            'severity' => $error->severity ?? 'ERROR',
                            'details' => [
                                'error_message' => $error->error_message,
                                'error_code' => $error->error_code,
                                'severity' => $error->severity ?? 'ERROR',
                                'node_uid' => $node->uid,
                                'hardware_id' => $node->hardware_id,
                                'count' => $newCount, // Используем максимальный count
                                'first_seen_at' => $firstSeenAt,
                                'last_seen_at' => $lastSeenAt,
                                'topic' => $error->topic,
                                'payload' => $error->last_payload,
                            ],
                        ]);
                    } else {
                        // Создаем новый алерт напрямую через модель, чтобы сохранить исходный count
                        \App\Models\Alert::create([
                            'zone_id' => $node->zone_id,
                            'source' => 'infra',
                            'code' => $alertCode,
                            'type' => 'Node Error: ' . ($error->error_message ?: 'Unknown error'),
                            'severity' => $error->severity ?? 'ERROR',
                            'status' => 'ACTIVE',
                            'details' => [
                                'error_message' => $error->error_message,
                                'error_code' => $error->error_code,
                                'severity' => $error->severity ?? 'ERROR',
                                'node_uid' => $node->uid,
                                'hardware_id' => $node->hardware_id,
                                'count' => $error->count ?? 1, // Сохраняем исходный count
                                'first_seen_at' => $firstSeenAt,
                                'last_seen_at' => $lastSeenAt,
                                'topic' => $error->topic,
                                'payload' => $error->last_payload,
                            ],
                        ]);
                    }
                    $alertsCreated++;
                }
                
                Log::info('Created alerts from unassigned errors', [
                    'node_id' => $node->id,
                    'zone_id' => $node->zone_id,
                    'hardware_id' => $node->hardware_id,
                    'errors_count' => $errors->count(),
                    'alerts_created' => $alertsCreated,
                ]);
                
                // Архивируем ошибки только после успешного создания alerts (когда есть zone_id)
                // Проверяем наличие таблицы архива перед архивированием
                if (DB::getSchemaBuilder()->hasTable('unassigned_node_errors_archive')) {
                    foreach ($errors as $error) {
                    DB::table('unassigned_node_errors_archive')->insert([
                        'hardware_id' => $error->hardware_id,
                        'error_message' => $error->error_message,
                        'error_code' => $error->error_code,
                        'severity' => $error->severity,
                        'topic' => $error->topic,
                        'last_payload' => $error->last_payload,
                        'count' => $error->count,
                        'first_seen_at' => $error->first_seen_at,
                        'last_seen_at' => $error->last_seen_at,
                        'node_id' => $node->id,
                        'attached_at' => now(),
                        'attached_zone_id' => $node->zone_id,
                        'archived_at' => now(),
                    ]);
                    }
                }
                
                // Удаляем записи из unassigned_node_errors только после успешного архивирования
                $deleted = DB::table('unassigned_node_errors')
                    ->where('hardware_id', $node->hardware_id)
                    ->whereNull('node_id')
                    ->delete();
                
                if ($deleted > 0) {
                    Log::info('Archived and removed unassigned errors', [
                        'node_id' => $node->id,
                        'hardware_id' => $node->hardware_id,
                        'errors_archived' => $deleted,
                    ]);
                    
                    // Создаем zone_event для прозрачности операции
                    try {
                        // Используем DB::table для zone_events, так как структура изменена (payload_json вместо details)
                        DB::table('zone_events')->insert([
                            'zone_id' => $node->zone_id,
                            'type' => 'unassigned_attached',
                            'entity_type' => 'unassigned_error',
                            'entity_id' => (string) $node->id,
                            'payload_json' => json_encode([
                                'node_id' => $node->id,
                                'node_uid' => $node->uid,
                                'hardware_id' => $node->hardware_id,
                                'errors_count' => $deleted,
                                'alerts_created' => $alertsCreated,
                            ]),
                            'server_ts' => now()->timestamp * 1000,
                            'created_at' => now(),
                        ]);
                    } catch (\Exception $e) {
                        // Логируем ошибку создания zone_event, но не прерываем процесс
                        Log::warning('Failed to create zone_event for unassigned_attached', [
                            'node_id' => $node->id,
                            'zone_id' => $node->zone_id,
                            'error' => $e->getMessage(),
                        ]);
                    }
                }
            }
            
        } catch (\Exception $e) {
            Log::warning('Failed to attach unassigned errors to node', [
                'node_id' => $node->id,
                'hardware_id' => $node->hardware_id,
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString()
            ]);
        }
    }

    /**
     * Public wrapper: attach накопленные ошибки неназначенного узла к ноде.
     * Используется при завершении привязки (binding completion), когда zone_id становится известен.
     */
    public function attachUnassignedErrorsForNode(DeviceNode $node): void
    {
        $this->attachUnassignedErrors($node);
    }
}
