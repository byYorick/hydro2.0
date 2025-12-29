<?php

namespace App\Services;

use App\Enums\NodeLifecycleState;
use App\Models\DeviceNode;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class NodeSwapService
{
    /**
     * Заменить узел новым узлом.
     * 
     * Логика:
     * - Найти старый узел по ID
     * - Найти новый узел по hardware_id (или создать)
     * - Перепривязать zone_id, channels (опционально)
     * - Пометить старый узел как DECOMMISSIONED
     * - Вернуть новый узел
     * 
     * @param int $oldNodeId ID старого узла
     * @param string $newHardwareId Hardware ID нового узла
     * @param array $options Дополнительные опции:
     *   - migrate_telemetry: bool (по умолчанию false) - мигрировать историю телеметрии
     *   - migrate_channels: bool (по умолчанию true) - перепривязать каналы
     * @return DeviceNode
     */
    public function swapNode(int $oldNodeId, string $newHardwareId, array $options = []): DeviceNode
    {
        return DB::transaction(function () use ($oldNodeId, $newHardwareId, $options) {
            // Находим старый узел
            $oldNode = DeviceNode::findOrFail($oldNodeId);
            
            // Находим или создаём новый узел по hardware_id
            $newNode = DeviceNode::where('hardware_id', $newHardwareId)->first();
            
            if (!$newNode) {
                // Создаём новый узел на основе старого
                $newNode = new DeviceNode();
                $newNode->uid = $this->generateNewNodeUid($oldNode);
                $newNode->hardware_id = $newHardwareId;
                $newNode->type = $oldNode->type;
                $newNode->name = $oldNode->name . ' (заменён)';
                $newNode->zone_id = $oldNode->zone_id;
                // НЕ переводим сразу в ASSIGNED_TO_ZONE - это произойдет только после получения config_report от ноды
                $newNode->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
                $newNode->validated = true;
                $newNode->first_seen_at = now();
                $newNode->save();
                
                Log::info('New node created during swap', [
                    'old_node_id' => $oldNodeId,
                    'new_node_id' => $newNode->id,
                    'new_hardware_id' => $newHardwareId,
                ]);
            } else {
                // Обновляем существующий узел
                if (!$newNode->zone_id && $oldNode->zone_id) {
                    $newNode->zone_id = $oldNode->zone_id;
                }
                // НЕ переводим сразу в ASSIGNED_TO_ZONE - это произойдет только после получения config_report от ноды
                // Если узел был в ASSIGNED_TO_ZONE или ACTIVE, переводим в REGISTERED_BACKEND,
                // чтобы конфиг был опубликован заново и нода подтвердила установку
                $previousState = $newNode->lifecycle_state;
                if ($newNode->lifecycle_state && 
                    in_array($newNode->lifecycle_state, [
                        NodeLifecycleState::ASSIGNED_TO_ZONE,
                        NodeLifecycleState::ACTIVE,
                        NodeLifecycleState::DEGRADED
                    ])) {
                    $newNode->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
                    Log::info('Node lifecycle reset to REGISTERED_BACKEND during swap to trigger config publish', [
                        'node_id' => $newNode->id,
                        'previous_state' => $previousState?->value,
                        'new_state' => NodeLifecycleState::REGISTERED_BACKEND->value,
                    ]);
                } elseif (!$newNode->lifecycle_state) {
                    $newNode->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
                }
                $newNode->save();
                
                Log::info('Existing node updated during swap', [
                    'old_node_id' => $oldNodeId,
                    'new_node_id' => $newNode->id,
                    'new_hardware_id' => $newHardwareId,
                ]);
            }
            
            // Перепривязываем каналы, если указано
            $migrateChannels = $options['migrate_channels'] ?? true;
            if ($migrateChannels) {
                $oldNode->channels()->update(['node_id' => $newNode->id]);
                Log::info('Channels migrated to new node', [
                    'old_node_id' => $oldNodeId,
                    'new_node_id' => $newNode->id,
                ]);
            }
            
            // Мигрируем историю телеметрии, если указано
            $migrateTelemetry = $options['migrate_telemetry'] ?? false;
            $telemetryMigrationResult = null;
            if ($migrateTelemetry) {
                $telemetryMigrationResult = $this->migrateTelemetryHistory($oldNode->id, $newNode->id);
                // Если миграция критична и не удалась, прерываем транзакцию
                if (!$telemetryMigrationResult['success']) {
                    throw new \DomainException(
                        'Telemetry migration failed: ' . ($telemetryMigrationResult['error'] ?? 'Unknown error')
                    );
                }
            }
            
            // Помечаем старый узел как DECOMMISSIONED
            $oldNode->lifecycle_state = NodeLifecycleState::DECOMMISSIONED;
            $oldNode->status = 'offline';
            $oldNode->save();
            
            Log::info('Node swap completed', [
                'old_node_id' => $oldNodeId,
                'old_uid' => $oldNode->uid,
                'new_node_id' => $newNode->id,
                'new_uid' => $newNode->uid,
                'new_hardware_id' => $newHardwareId,
                'telemetry_migrated' => $migrateTelemetry,
                'telemetry_migration_success' => $telemetryMigrationResult['success'] ?? null,
            ]);
            
            // Возвращаем результат с информацией о миграции
            $newNode->setAttribute('_swap_metadata', [
                'telemetry_migrated' => $migrateTelemetry,
                'telemetry_migration_success' => $telemetryMigrationResult['success'] ?? null,
                'telemetry_migration_warning' => $telemetryMigrationResult['warning'] ?? null,
            ]);
            
            return $newNode;
        });
    }
    
    /**
     * Мигрировать историю телеметрии от старого узла к новому.
     * 
     * @param int $oldNodeId
     * @param int $newNodeId
     * @return array ['success' => bool, 'error' => string|null, 'warning' => string|null]
     */
    private function migrateTelemetryHistory(int $oldNodeId, int $newNodeId): array
    {
        try {
            // Подсчитываем количество записей для миграции
            $samplesCount = DB::table('telemetry_samples')
                ->where('node_id', $oldNodeId)
                ->count();
            
            $lastCount = DB::table('telemetry_last')
                ->where('node_id', $oldNodeId)
                ->count();
            
            // Обновляем telemetry_samples
            $samplesUpdated = DB::table('telemetry_samples')
                ->where('node_id', $oldNodeId)
                ->update(['node_id' => $newNodeId]);
            
            // Обновляем telemetry_last
            $lastUpdated = DB::table('telemetry_last')
                ->where('node_id', $oldNodeId)
                ->update(['node_id' => $newNodeId]);
            
            // Проверяем, что все записи были обновлены
            $warning = null;
            if ($samplesUpdated !== $samplesCount) {
                $warning = "Expected to migrate {$samplesCount} telemetry_samples, but only {$samplesUpdated} were updated.";
                Log::warning('Telemetry migration: samples count mismatch', [
                    'old_node_id' => $oldNodeId,
                    'new_node_id' => $newNodeId,
                    'expected' => $samplesCount,
                    'updated' => $samplesUpdated,
                ]);
            }
            
            if ($lastUpdated !== $lastCount) {
                $warning = ($warning ? $warning . ' ' : '') . 
                    "Expected to migrate {$lastCount} telemetry_last records, but only {$lastUpdated} were updated.";
                Log::warning('Telemetry migration: last records count mismatch', [
                    'old_node_id' => $oldNodeId,
                    'new_node_id' => $newNodeId,
                    'expected' => $lastCount,
                    'updated' => $lastUpdated,
                ]);
            }
            
            Log::info('Telemetry history migrated', [
                'old_node_id' => $oldNodeId,
                'new_node_id' => $newNodeId,
                'samples_migrated' => $samplesUpdated,
                'last_migrated' => $lastUpdated,
            ]);
            
            return [
                'success' => true,
                'error' => null,
                'warning' => $warning,
                'samples_migrated' => $samplesUpdated,
                'last_migrated' => $lastUpdated,
            ];
        } catch (\Exception $e) {
            Log::error('Failed to migrate telemetry history', [
                'old_node_id' => $oldNodeId,
                'new_node_id' => $newNodeId,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
                'trace' => $e->getTraceAsString(),
            ]);
            
            // Возвращаем информацию об ошибке для обработки вызывающим кодом
            return [
                'success' => false,
                'error' => $e->getMessage(),
                'warning' => null,
            ];
        }
    }
    
    /**
     * Генерировать новый uid для заменённого узла.
     * 
     * @param DeviceNode $oldNode
     * @return string
     */
    private function generateNewNodeUid(DeviceNode $oldNode): string
    {
        // Используем префикс из старого uid и добавляем суффикс
        $baseUid = $oldNode->uid;
        $counter = 1;
        
        do {
            $newUid = $baseUid . "-swap{$counter}";
            $exists = DeviceNode::where('uid', $newUid)->exists();
            $counter++;
        } while ($exists && $counter < 100);
        
        return $newUid;
    }
}
