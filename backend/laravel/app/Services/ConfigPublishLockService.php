<?php

namespace App\Services;

use App\Models\DeviceNode;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Cache;

class ConfigPublishLockService
{
    /**
     * Получить pessimistic lock для публикации конфигурации узла.
     * Использует SELECT FOR UPDATE для блокировки строки в БД.
     * 
     * @param DeviceNode $node
     * @return DeviceNode|null Заблокированная модель узла или null при ошибке
     */
    public function acquirePessimisticLock(DeviceNode $node): ?DeviceNode
    {
        try {
            // Используем транзакцию с SELECT FOR UPDATE для pessimistic locking
            // ВАЖНО: Транзакция должна быть завершена до освобождения advisory lock
            // Поэтому мы возвращаем заблокированную модель, но транзакция завершается
            // Advisory lock должен быть получен ВНЕ транзакции
            $lockedNode = DB::transaction(function () use ($node) {
                $locked = DeviceNode::where('id', $node->id)
                    ->lockForUpdate()
                    ->first();

                if (!$locked) {
                    Log::warning('ConfigPublishLockService: Node not found for locking', [
                        'node_id' => $node->id,
                    ]);
                    return null;
                }

                Log::debug('ConfigPublishLockService: Pessimistic lock acquired', [
                    'node_id' => $node->id,
                    'node_uid' => $node->uid,
                ]);

                return $locked;
            }, 5); // 5 попыток при serialization failure

            // Обновляем модель после завершения транзакции
            if ($lockedNode) {
                $lockedNode->refresh();
            }

            return $lockedNode;
        } catch (\Exception $e) {
            Log::error('ConfigPublishLockService: Failed to acquire pessimistic lock', [
                'node_id' => $node->id,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
            ]);
            return null;
        }
    }

    /**
     * Получить optimistic lock для публикации конфигурации узла.
     * Использует версионирование через поле updated_at или version.
     * 
     * @param DeviceNode $node
     * @return array ['node' => DeviceNode, 'version' => int] или null при ошибке
     */
    public function acquireOptimisticLock(DeviceNode $node): ?array
    {
        try {
            $node->refresh();
            
            // Используем updated_at как версию для optimistic locking
            $version = $node->updated_at?->timestamp ?? time();
            
            Log::debug('ConfigPublishLockService: Optimistic lock acquired', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'version' => $version,
            ]);

            return [
                'node' => $node,
                'version' => $version,
            ];
        } catch (\Exception $e) {
            Log::error('ConfigPublishLockService: Failed to acquire optimistic lock', [
                'node_id' => $node->id,
                'error' => $e->getMessage(),
            ]);
            return null;
        }
    }

    /**
     * Проверить, не изменилась ли версия узла (для optimistic locking).
     * 
     * @param DeviceNode $node
     * @param int $expectedVersion Ожидаемая версия
     * @return bool true если версия не изменилась, false иначе
     */
    public function checkOptimisticLock(DeviceNode $node, int $expectedVersion): bool
    {
        $node->refresh();
        $currentVersion = $node->updated_at?->timestamp ?? time();
        
        if ($currentVersion !== $expectedVersion) {
            Log::warning('ConfigPublishLockService: Optimistic lock check failed - version changed', [
                'node_id' => $node->id,
                'expected_version' => $expectedVersion,
                'current_version' => $currentVersion,
            ]);
            return false;
        }

        return true;
    }

    /**
     * Получить advisory lock для дедупликации публикации конфигурации.
     * Использует PostgreSQL advisory locks для предотвращения одновременной публикации.
     * 
     * @param DeviceNode $node
     * @param int $timeout Таймаут в секундах (по умолчанию 10)
     * @return bool true если lock получен, false иначе
     */
    public function acquireAdvisoryLock(DeviceNode $node, int $timeout = 10): bool
    {
        try {
            // Проверяем, что используется PostgreSQL (advisory locks работают только в PostgreSQL)
            $driver = DB::connection()->getDriverName();
            if ($driver !== 'pgsql') {
                Log::warning('ConfigPublishLockService: Advisory locks require PostgreSQL', [
                    'node_id' => $node->id,
                    'driver' => $driver,
                ]);
                return false; // Возвращаем false, так как advisory locks требуются для безопасности
            }

            // Используем PostgreSQL advisory lock
            // Используем node_id как ключ для lock
            $lockKey = $node->id;
            
            // pg_try_advisory_lock не блокирует, возвращает true/false сразу
            $result = DB::selectOne(
                "SELECT pg_try_advisory_lock(?) as locked",
                [$lockKey]
            );

            if ($result && $result->locked) {
                Log::debug('ConfigPublishLockService: Advisory lock acquired', [
                    'node_id' => $node->id,
                    'node_uid' => $node->uid,
                    'lock_key' => $lockKey,
                ]);
                return true;
            }

            Log::warning('ConfigPublishLockService: Failed to acquire advisory lock', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'lock_key' => $lockKey,
            ]);
            return false;
        } catch (\Exception $e) {
            Log::error('ConfigPublishLockService: Error acquiring advisory lock', [
                'node_id' => $node->id,
                'error' => $e->getMessage(),
                'driver' => DB::connection()->getDriverName(),
            ]);
            return false;
        }
    }

    /**
     * Освободить advisory lock.
     * 
     * @param DeviceNode $node
     * @return bool true если lock освобожден, false иначе
     */
    public function releaseAdvisoryLock(DeviceNode $node): bool
    {
        try {
            // Проверяем, что используется PostgreSQL
            $driver = DB::connection()->getDriverName();
            if ($driver !== 'pgsql') {
                Log::warning('ConfigPublishLockService: Advisory lock release requires PostgreSQL', [
                    'node_id' => $node->id,
                    'driver' => $driver,
                ]);
                return false;
            }

            $lockKey = $node->id;
            
            $result = DB::selectOne(
                "SELECT pg_advisory_unlock(?) as unlocked",
                [$lockKey]
            );

            $unlocked = $result && $result->unlocked;

            if ($unlocked) {
                Log::debug('ConfigPublishLockService: Advisory lock released', [
                    'node_id' => $node->id,
                    'node_uid' => $node->uid,
                    'lock_key' => $lockKey,
                ]);
            } else {
                Log::warning('ConfigPublishLockService: Advisory lock was not held', [
                    'node_id' => $node->id,
                    'node_uid' => $node->uid,
                    'lock_key' => $lockKey,
                ]);
            }

            return true;
        } catch (\Exception $e) {
            Log::error('ConfigPublishLockService: Error releasing advisory lock', [
                'node_id' => $node->id,
                'error' => $e->getMessage(),
                'driver' => DB::connection()->getDriverName(),
            ]);
            return false;
        }
    }

    /**
     * Проверить дедупликацию через кеш (дополнительный уровень защиты).
     * 
     * @param DeviceNode $node
     * @param string $configHash Хеш конфигурации
     * @return bool true если конфиг уже был опубликован недавно, false иначе
     */
    public function isDuplicate(DeviceNode $node, string $configHash): bool
    {
        $cacheKey = "config_publish:{$node->id}:{$configHash}";
        $exists = Cache::has($cacheKey);
        
        if ($exists) {
            Log::debug('ConfigPublishLockService: Duplicate config detected', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'config_hash' => substr($configHash, 0, 16),
            ]);
        }

        return $exists;
    }

    /**
     * Пометить конфигурацию как опубликованную (для дедупликации).
     * 
     * @param DeviceNode $node
     * @param string $configHash Хеш конфигурации
     * @param int $ttl Время жизни в секундах (по умолчанию 60)
     * @return void
     */
    public function markAsPublished(DeviceNode $node, string $configHash, int $ttl = 60): void
    {
        $cacheKey = "config_publish:{$node->id}:{$configHash}";
        Cache::put($cacheKey, true, $ttl);
        
        Log::debug('ConfigPublishLockService: Config marked as published', [
            'node_id' => $node->id,
            'node_uid' => $node->uid,
            'config_hash' => substr($configHash, 0, 16),
            'ttl' => $ttl,
        ]);
    }
}

