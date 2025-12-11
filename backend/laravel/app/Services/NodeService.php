<?php

namespace App\Services;

use App\Models\DeviceNode;
use App\Services\NodeLifecycleService;
use App\Enums\NodeLifecycleState;
use App\Events\NodeConfigUpdated;
use App\Helpers\TransactionHelper;
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
            // Используем точечную очистку вместо глобального flush для предотвращения DoS
            try {
                \Illuminate\Support\Facades\Cache::tags(['devices_list'])->flush();
            } catch (\BadMethodCallException $e) {
                // Если теги не поддерживаются, очищаем только конкретные ключи
                $cacheKeys = [
                    'devices_list_all',
                    'devices_list_unassigned',
                ];
                foreach ($cacheKeys as $key) {
                    \Illuminate\Support\Facades\Cache::forget($key);
                }
                // НЕ используем Cache::flush() - это может привести к DoS при массовых обновлениях
            }
            
            return $node;
        });
    }

    /**
     * Обновить узел
     */
    public function update(DeviceNode $node, array $data): DeviceNode
    {
        // Используем SERIALIZABLE isolation level для критичной операции обновления узла
        // с retry логикой на serialization failures
        return TransactionHelper::withSerializableRetry(function () use ($node, $data) {
            
            // Блокируем строку для предотвращения lost updates
            $node = DeviceNode::where('id', $node->id)
                ->lockForUpdate()
                ->first();
            
            if (!$node) {
                throw new \RuntimeException('Node not found');
            }
            
            Log::info('NodeService::update START', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'incoming_data' => $data,
                'current_zone_id' => $node->zone_id,
                'current_lifecycle' => $node->lifecycle_state?->value,
            ]);
            
            $oldZoneId = $node->zone_id;
            
            /**
             * ВАЖНАЯ ЛОГИКА: Разделяем привязку от UI и обновление от History Logger
             * 
             * Сценарий 1: Пользователь привязывает/перепривязывает узел к зоне (UI)
             *   - Приходит: {"zone_id": 6} (БЕЗ pending_zone_id в запросе)
             *   - Устанавливаем: pending_zone_id = 6, zone_id = null
             *   - Публикуется конфиг
             *   - Узел получает конфиг и отправляет config_response
             *   - History Logger делает финализацию
             * 
             * Сценарий 2: History Logger завершает привязку после config_response
             *   - Приходит: {"zone_id": 6, "pending_zone_id": null} (С pending_zone_id в запросе)
             *   - Устанавливаем: zone_id = 6, pending_zone_id = null
             *   - Конфиг НЕ публикуется (узел уже имеет конфиг)
             */
            
            $hasZoneIdInRequest = array_key_exists('zone_id', $data);
            $hasPendingZoneIdInRequest = array_key_exists('pending_zone_id', $data);
            $newZoneId = $hasZoneIdInRequest ? $data['zone_id'] : null;
            $newPendingZoneId = $hasPendingZoneIdInRequest ? $data['pending_zone_id'] : null;
            $oldPendingZoneId = $node->pending_zone_id;
            
            /**
             * КРИТИЧНО: Если в запросе есть zone_id, но НЕТ pending_zone_id - это ВСЕГДА запрос от UI
             * Не важно, первая это привязка или перепривязка - всегда через pending_zone_id
             * Если в запросе есть И zone_id И pending_zone_id - это завершение привязки от History Logger
             */
            // Не важно, первая это привязка или переприв язка - всегда через pending_zone_id
            // Если в запросе есть И zone_id И pending_zone_id - это завершение привязки от History Logger
            $isAssignmentFromUI = $hasZoneIdInRequest && !$hasPendingZoneIdInRequest && $newZoneId;
            $isBindingCompletion = $hasZoneIdInRequest && $hasPendingZoneIdInRequest && $newZoneId && $newPendingZoneId === null;
            
            Log::info('NodeService::update zone assignment check', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'hasZoneIdInRequest' => $hasZoneIdInRequest,
                'hasPendingZoneIdInRequest' => $hasPendingZoneIdInRequest,
                'newZoneId' => $newZoneId,
                'newPendingZoneId' => $newPendingZoneId,
                'oldZoneId' => $oldZoneId,
                'oldPendingZoneId' => $oldPendingZoneId,
                'isAssignmentFromUI' => $isAssignmentFromUI,
                'isBindingCompletion' => $isBindingCompletion,
                'lifecycle_state' => $node->lifecycle_state?->value,
            ]);
            
            if ($isAssignmentFromUI) {
                // Проверяем lifecycle state - допускаются REGISTERED_BACKEND и ASSIGNED_TO_ZONE (переприв язка)
                $currentState = $node->lifecycleState();
                $canAssign = in_array($currentState, [
                    NodeLifecycleState::REGISTERED_BACKEND,
                    NodeLifecycleState::ASSIGNED_TO_ZONE,
                    NodeLifecycleState::ACTIVE,
                ]);
                
                if (!$canAssign) {
                    Log::warning('Cannot assign node to zone - invalid lifecycle state', [
                        'node_id' => $node->id,
                        'requested_zone_id' => $newZoneId,
                        'current_state' => $currentState->value,
                        'allowed_states' => ['REGISTERED_BACKEND', 'ASSIGNED_TO_ZONE', 'ACTIVE'],
                    ]);
                    throw new \DomainException("Cannot assign node to zone in current state: {$currentState->value}");
                }
                
                /**
                 * КРИТИЧНО: ВСЕГДА сохраняем в pending_zone_id для получения подтверждения от ноды
                 * zone_id будет обновлен только после config_response от ноды
                 */
                $data['pending_zone_id'] = $newZoneId;
                unset($data['zone_id']); // Удаляем zone_id из данных обновления!
                
                // Если это переприв язка (был старый zone_id), сбрасываем в REGISTERED_BACKEND
                if ($oldZoneId && $oldZoneId != $newZoneId) {
                    $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
                    $node->zone_id = null; // Явно очищаем старый zone_id
                    Log::info('Node re-assignment: reset to REGISTERED_BACKEND, waiting for confirmation', [
                        'node_id' => $node->id,
                        'old_zone_id' => $oldZoneId,
                        'pending_zone_id' => $newZoneId,
                    ]);
                } else {
                    // Первичная привязка
                    $node->zone_id = null; // Явно очищаем zone_id
                }
                
                Log::info('UI zone assignment: set pending_zone_id, waiting for node confirmation', [
                    'node_id' => $node->id,
                    'pending_zone_id' => $newZoneId,
                    'old_zone_id' => $oldZoneId,
                    'lifecycle_state' => $node->lifecycle_state?->value,
                ]);
            }
            
            $node->update($data);
            
            // БАГ #2 FIX: Убрана дублирующая публикация конфига
            // Публикация происходит только через событие NodeConfigUpdated в DeviceNode::saved
            // Это предотвращает двойную публикацию конфига
            // if ($isAssignmentFromUI) {
            //     \App\Jobs\PublishNodeConfigJob::dispatch($node->id);
            // }
            
            // Логируем завершение привязки от history-logger (когда zone_id устанавливается и pending_zone_id очищается)
            if ($isBindingCompletion && $node->zone_id && !$node->pending_zone_id) {
                Log::info('NodeService: Binding completed by history-logger (zone_id set, pending_zone_id cleared)', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                    'zone_id' => $node->zone_id,
                    'old_zone_id' => $oldZoneId,
                    'old_pending_zone_id' => $oldPendingZoneId,
                    'new_zone_id' => $node->zone_id,
                    'new_pending_zone_id' => $node->pending_zone_id,
                    'lifecycle_state' => $node->lifecycle_state?->value,
                    'reason' => 'History-logger completed node binding after config_response',
                ]);
            }
            
            /**
             * Если узел отвязан от зоны (zone_id стал null), но НЕ при привязке от UI
             * КРИТИЧНО: Не срабатывает при привязке от UI, так как там pending_zone_id установлен
             */
            if (!$node->zone_id && $oldZoneId && !$isAssignmentFromUI) {
                // Сбрасываем lifecycle_state в REGISTERED_BACKEND, чтобы нода считалась новой
                $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
                $node->pending_zone_id = null; // Очищаем pending_zone_id при отвязке
                $node->save();
                
                Log::info('Node detached from zone via update, reset to REGISTERED_BACKEND', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                    'old_zone_id' => $oldZoneId,
                    'old_pending_zone_id' => $oldPendingZoneId,
                    'new_lifecycle_state' => $node->lifecycle_state?->value,
                ]);
            }
            
            Log::info('Node updated', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'zone_id' => $node->zone_id,
                'pending_zone_id' => $node->pending_zone_id,
                'lifecycle_state' => $node->lifecycle_state?->value,
            ]);
            
            /**
             * Очищаем кеш списка устройств для всех пользователей
             * Используем теги для точечной очистки, если поддерживаются
             */
            try {
                \Illuminate\Support\Facades\Cache::tags(['devices_list'])->flush();
            } catch (\BadMethodCallException $e) {
                // Если теги не поддерживаются, очищаем весь кеш
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
            $oldPendingZoneId = $node->pending_zone_id;
            
            // Если нода уже отвязана (нет ни zone_id, ни pending_zone_id), ничего не делаем
            if (!$oldZoneId && !$oldPendingZoneId) {
                Log::info('Node already detached', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                ]);
                return $node;
            }
            
            // Отвязываем от зоны
            $node->zone_id = null;
            
            /**
             * КРИТИЧНО: Очищаем pending_zone_id при отвязке
             * Если нода была в процессе привязки (pending_zone_id установлен, но zone_id еще null),
             * необходимо очистить pending_zone_id, чтобы избежать проблем
             */
            $node->pending_zone_id = null;
            
            // Сбрасываем lifecycle_state в REGISTERED_BACKEND, чтобы нода считалась новой
            // Это позволит ей снова появиться в списке новых нод для привязки
            $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
            
            $node->save();
            
            Log::info('Node detached from zone', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'old_zone_id' => $oldZoneId,
                'old_pending_zone_id' => $oldPendingZoneId,
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

