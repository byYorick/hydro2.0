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
                $newNode->lifecycle_state = NodeLifecycleState::ASSIGNED_TO_ZONE;
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
                if ($newNode->lifecycle_state === NodeLifecycleState::REGISTERED_BACKEND && $newNode->zone_id) {
                    $newNode->lifecycle_state = NodeLifecycleState::ASSIGNED_TO_ZONE;
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
            if ($migrateTelemetry) {
                $this->migrateTelemetryHistory($oldNode->id, $newNode->id);
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
            ]);
            
            return $newNode;
        });
    }
    
    /**
     * Мигрировать историю телеметрии от старого узла к новому.
     * 
     * @param int $oldNodeId
     * @param int $newNodeId
     * @return void
     */
    private function migrateTelemetryHistory(int $oldNodeId, int $newNodeId): void
    {
        try {
            // Обновляем telemetry_samples
            DB::table('telemetry_samples')
                ->where('node_id', $oldNodeId)
                ->update(['node_id' => $newNodeId]);
            
            // Обновляем telemetry_last
            DB::table('telemetry_last')
                ->where('node_id', $oldNodeId)
                ->update(['node_id' => $newNodeId]);
            
            Log::info('Telemetry history migrated', [
                'old_node_id' => $oldNodeId,
                'new_node_id' => $newNodeId,
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to migrate telemetry history', [
                'old_node_id' => $oldNodeId,
                'new_node_id' => $newNodeId,
                'error' => $e->getMessage(),
            ]);
            // Не прерываем транзакцию, только логируем ошибку
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

