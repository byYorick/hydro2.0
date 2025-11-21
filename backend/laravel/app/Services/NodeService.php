<?php

namespace App\Services;

use App\Models\DeviceNode;
use App\Services\NodeLifecycleService;
use App\Enums\NodeLifecycleState;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class NodeService
{
    public function __construct(
        private NodeLifecycleService $lifecycleService
    ) {
    }

    /**
     * Создать/зарегистрировать узел
     */
    public function create(array $data): DeviceNode
    {
        return DB::transaction(function () use ($data) {
            $node = DeviceNode::create($data);
            Log::info('Node created', ['node_id' => $node->id, 'uid' => $node->uid]);
            
            // Очищаем кеш списка устройств для всех пользователей
            // Используем паттерн для очистки всех ключей devices_list_*
            try {
                \Illuminate\Support\Facades\Cache::tags(['devices_list'])->flush();
            } catch (\BadMethodCallException $e) {
                // Если теги не поддерживаются, очищаем все ключи с паттерном
                // В production лучше использовать Redis с тегами
                \Illuminate\Support\Facades\Cache::flush();
            }
            
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
                // Используем NodeLifecycleService для безопасного перехода
                $currentState = $node->lifecycleState();
                if ($currentState === NodeLifecycleState::REGISTERED_BACKEND) {
                    $this->lifecycleService->transitionToAssigned(
                        $node,
                        'Node assigned to zone via NodeService::update'
                    );
                } elseif ($currentState === NodeLifecycleState::ASSIGNED_TO_ZONE) {
                    // Узел уже в правильном состоянии
                    Log::debug('Node already in ASSIGNED_TO_ZONE state', [
                        'node_id' => $node->id,
                        'zone_id' => $node->zone_id,
                    ]);
                } else {
                    // Попытка присвоить узел, который не в правильном состоянии
                    Log::warning('Cannot assign node to zone - invalid lifecycle state', [
                        'node_id' => $node->id,
                        'zone_id' => $node->zone_id,
                        'current_state' => $currentState->value,
                        'required_state' => NodeLifecycleState::REGISTERED_BACKEND->value,
                    ]);
                    // Можно выбросить исключение, но для обратной совместимости оставляем как есть
                }
            }
            
            Log::info('Node updated', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'zone_id' => $node->zone_id,
                'lifecycle_state' => $node->lifecycle_state?->value,
            ]);
            
            // Очищаем кеш списка устройств для всех пользователей
            try {
                \Illuminate\Support\Facades\Cache::tags(['devices_list'])->flush();
            } catch (\BadMethodCallException $e) {
                // Если теги не поддерживаются, очищаем все ключи с паттерном
                \Illuminate\Support\Facades\Cache::flush();
            }
            
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


