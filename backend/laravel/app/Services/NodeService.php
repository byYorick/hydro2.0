<?php

namespace App\Services;

use App\Models\DeviceNode;
use App\Services\NodeLifecycleService;
use App\Enums\NodeLifecycleState;
use App\Events\NodeConfigUpdated;
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
            
            // Если узел отвязан от зоны (zone_id стал null)
            if (!$node->zone_id && $oldZoneId) {
                // Сбрасываем lifecycle_state в REGISTERED_BACKEND, чтобы нода считалась новой
                $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
                $node->save();
                
                Log::info('Node detached from zone via update, reset to REGISTERED_BACKEND', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                    'old_zone_id' => $oldZoneId,
                    'new_lifecycle_state' => $node->lifecycle_state?->value,
                ]);
            }
            // Если узел привязан к зоне и раньше не был привязан
            // НЕ переводим сразу в ASSIGNED_TO_ZONE - это произойдет только после успешной публикации конфига
            elseif ($node->zone_id && !$oldZoneId) {
                $currentState = $node->lifecycleState();
                
                // Проверяем, что узел в правильном состоянии для привязки
                if ($currentState !== NodeLifecycleState::REGISTERED_BACKEND) {
                    Log::warning('Cannot assign node to zone - invalid lifecycle state', [
                        'node_id' => $node->id,
                        'zone_id' => $node->zone_id,
                        'current_state' => $currentState->value,
                        'required_state' => NodeLifecycleState::REGISTERED_BACKEND->value,
                    ]);
                    // Откатываем привязку к зоне, если состояние неправильное
                    $node->zone_id = null;
                    $node->save();
                    throw new \DomainException("Cannot assign node to zone: node must be in REGISTERED_BACKEND state");
                }
                
                // Оставляем в REGISTERED_BACKEND - переход в ASSIGNED_TO_ZONE произойдет
                // только после успешной публикации конфига через PublishNodeConfigOnUpdate
                Log::info('Node zone_id updated, waiting for config publish', [
                    'node_id' => $node->id,
                    'zone_id' => $node->zone_id,
                    'lifecycle_state' => $node->lifecycle_state?->value,
                ]);
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
     * Отвязать узел от зоны.
     * При отвязке нода сбрасывается в REGISTERED_BACKEND и считается новой.
     */
    public function detach(DeviceNode $node): DeviceNode
    {
        return DB::transaction(function () use ($node) {
            $oldZoneId = $node->zone_id;
            
            if (!$oldZoneId) {
                Log::info('Node already detached', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                ]);
                return $node;
            }
            
            // Отвязываем от зоны
            $node->zone_id = null;
            
            // Сбрасываем lifecycle_state в REGISTERED_BACKEND, чтобы нода считалась новой
            // Это позволит ей снова появиться в списке новых нод для привязки
            $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
            
            $node->save();
            
            Log::info('Node detached from zone', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'old_zone_id' => $oldZoneId,
                'new_lifecycle_state' => $node->lifecycle_state?->value,
            ]);
            
            // Очищаем кеш списка устройств
            try {
                \Illuminate\Support\Facades\Cache::tags(['devices_list'])->flush();
            } catch (\BadMethodCallException $e) {
                \Illuminate\Support\Facades\Cache::flush();
            }
            
            // Генерируем событие для обновления фронтенда через WebSocket
            event(new NodeConfigUpdated($node->fresh()));
            
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


