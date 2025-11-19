<?php

namespace App\Services;

use App\Models\DeviceNode;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class NodeService
{
    /**
     * Создать/зарегистрировать узел
     */
    public function create(array $data): DeviceNode
    {
        return DB::transaction(function () use ($data) {
            $node = DeviceNode::create($data);
            Log::info('Node created', ['node_id' => $node->id, 'uid' => $node->uid]);
            return $node;
        });
    }

    /**
     * Обновить узел
     */
    public function update(DeviceNode $node, array $data): DeviceNode
    {
        return DB::transaction(function () use ($node, $data) {
            $oldZoneId = $node->zone_id;
            $node->update($data);
            
            // Если узел привязан к зоне и раньше не был привязан, обновляем lifecycle_state
            if ($node->zone_id && !$oldZoneId) {
                // Переводим узел в состояние ASSIGNED_TO_ZONE
                if ($node->lifecycle_state === \App\Enums\NodeLifecycleState::REGISTERED_BACKEND) {
                    $node->lifecycle_state = \App\Enums\NodeLifecycleState::ASSIGNED_TO_ZONE;
                    $node->save();
                    Log::info('Node lifecycle state updated to ASSIGNED_TO_ZONE', [
                        'node_id' => $node->id,
                        'uid' => $node->uid,
                        'zone_id' => $node->zone_id,
                    ]);
                }
            }
            
            Log::info('Node updated', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'zone_id' => $node->zone_id,
                'lifecycle_state' => $node->lifecycle_state?->value,
            ]);
            return $node->fresh();
        });
    }

    /**
     * Удалить узел (с проверкой инвариантов)
     */
    public function delete(DeviceNode $node): void
    {
        DB::transaction(function () use ($node) {
            // Проверка: нельзя удалить узел, который привязан к зоне
            if ($node->zone_id) {
                throw new \DomainException('Cannot delete node that is attached to a zone. Please detach from zone first.');
            }

            $nodeId = $node->id;
            $nodeUid = $node->uid;
            $node->delete();
            Log::info('Node deleted', ['node_id' => $nodeId, 'uid' => $nodeUid]);
        });
    }
}

