<?php

namespace App\Services;

use App\Enums\NodeLifecycleState;
use App\Events\NodeConfigUpdated;
use App\Helpers\TransactionHelper;
use App\Models\DeviceNode;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class NodeService
{
    public function __construct(
        private NodeLifecycleService $lifecycleService,
        private NodeRegistryService $registryService,
        private NodeFirmwareUnbindService $firmwareUnbindService,
        private NodeSecretService $nodeSecretService,
    ) {}

    /**
     * Targeted invalidation для кеша списка устройств.
     *
     * S2.1 (AUDIT_2026_05_28_BUGFIX_PLAN): раньше использовался
     * `Cache::flush()` как fallback, если cache driver не поддерживает теги
     * (file/array/database). Это полный wipe shared cache, что выбивает
     * сессии, rate-limit counters, scheduler state и т.д. → de facto DoS.
     *
     * Корректная стратегия:
     *  1. Если cache driver поддерживает теги (Redis/Memcached) — `tags(...)->flush()`.
     *  2. Иначе — `Cache::forget()` только по известным fixed-ключам.
     *  3. Per-user ключи (`devices_list_<userId>`) имеют TTL=2-10 сек и сами
     *     быстро освежатся; их не трогаем — было бы O(users) вызовов.
     */
    private function invalidateDevicesListCache(?int $affectedZoneId = null): void
    {
        try {
            Cache::tags(['devices_list'])->flush();

            return;
        } catch (\BadMethodCallException $e) {
            // driver без поддержки тегов → targeted forget ниже
        }

        $keys = [
            'devices_list_all',
            'devices_list_unassigned',
        ];
        if ($affectedZoneId !== null) {
            $keys[] = 'devices_list_zone_'.$affectedZoneId;
        }

        foreach ($keys as $key) {
            Cache::forget($key);
        }
    }

    /**
     * Создать/зарегистрировать узел
     */
    public function create(array $data): DeviceNode
    {
        return DB::transaction(function () use ($data) {
            $node = DeviceNode::create($data);
            $this->nodeSecretService->ensureOnNode($node);
            if ($node->isDirty('config')) {
                $node->save();
            }
            Log::info('Node created', ['node_id' => $node->id, 'uid' => $node->uid]);

            // S2.1 (AUDIT_2026_05_28_BUGFIX_PLAN): targeted cache invalidation,
            // никогда `Cache::flush()`. См. NodeService::invalidateDevicesListCache().
            $this->invalidateDevicesListCache($node->zone_id);

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
        $unbindFromZoneId = null;
        $updated = TransactionHelper::withSerializableRetry(function () use ($node, $data, &$unbindFromZoneId) {

            // Блокируем строку для предотвращения lost updates
            $node = DeviceNode::where('id', $node->id)
                ->lockForUpdate()
                ->first();

            if (! $node) {
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
             * ВАЖНАЯ ЛОГИКА: Разделяем UI bind/rebind и финализацию bind в Laravel.
             *
             * Сценарий 1: Пользователь привязывает/перепривязывает узел к зоне (UI)
             *   - Приходит: {"zone_id": 6} (БЕЗ pending_zone_id в запросе)
             *   - Устанавливаем: pending_zone_id = 6, zone_id = null
             *   - Узел публикует config_report после подключения/инициализации
             *   - Laravel завершает bind после ingest-сигнала о наблюдённом config_report
             *
             * Сценарий 2: Laravel завершает bind после config_report
             *   - Приходит: {"zone_id": 6, "pending_zone_id": null} (с pending_zone_id в запросе)
             *   - Устанавливаем: zone_id = 6, pending_zone_id = null
             *   - Конфиг НЕ публикуется (узел уже имеет конфиг)
             */
            $hasZoneIdInRequest = array_key_exists('zone_id', $data);
            $hasPendingZoneIdInRequest = array_key_exists('pending_zone_id', $data);
            $newZoneId = $hasZoneIdInRequest ? $data['zone_id'] : null;
            $newPendingZoneId = $hasPendingZoneIdInRequest ? $data['pending_zone_id'] : null;
            $oldPendingZoneId = $node->pending_zone_id;
            $shouldRepublishConfig = false;

            /**
             * КРИТИЧНО: Если в запросе есть zone_id, но НЕТ pending_zone_id - это ВСЕГДА запрос от UI.
             * Не важно, первая это привязка или перепривязка - всегда через pending_zone_id.
             * Если в запросе есть И zone_id И pending_zone_id - это завершение привязки внутри Laravel.
             */
            $isAssignmentFromUI = $hasZoneIdInRequest && ! $hasPendingZoneIdInRequest && $newZoneId;
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

                if (! $canAssign) {
                    Log::warning('Cannot assign node to zone - invalid lifecycle state', [
                        'node_id' => $node->id,
                        'requested_zone_id' => $newZoneId,
                        'current_state' => $currentState->value,
                        'allowed_states' => ['REGISTERED_BACKEND', 'ASSIGNED_TO_ZONE', 'ACTIVE'],
                    ]);
                    throw new \DomainException("Cannot assign node to zone in current state: {$currentState->value}");
                }

                $sameStableZoneAssignment = $oldZoneId
                    && (int) $oldZoneId === (int) $newZoneId
                    && ! $oldPendingZoneId;
                $samePendingZoneAssignment = ! $oldZoneId
                    && $oldPendingZoneId
                    && (int) $oldPendingZoneId === (int) $newZoneId;

                unset($data['zone_id']); // UI bind flow никогда не пишет zone_id напрямую

                if ($sameStableZoneAssignment) {
                    Log::info('UI zone assignment is idempotent: node already assigned to requested zone', [
                        'node_id' => $node->id,
                        'uid' => $node->uid,
                        'zone_id' => $oldZoneId,
                        'lifecycle_state' => $currentState->value,
                    ]);
                } elseif ($samePendingZoneAssignment) {
                    $data['pending_zone_id'] = $newZoneId;

                    $this->transitionLifecycleToRegistered(
                        $node,
                        'pending_bind_retry_normalize'
                    );

                    $shouldRepublishConfig = true;

                    Log::info('UI zone assignment retry: node already pending requested zone, config will be republished', [
                        'node_id' => $node->id,
                        'uid' => $node->uid,
                        'pending_zone_id' => $newZoneId,
                        'lifecycle_state' => $node->lifecycle_state?->value,
                    ]);
                } else {
                    app(ZoneNodeAutomationBindingValidator::class)->assertBindAllowed($node, (int) $newZoneId);

                    /**
                     * КРИТИЧНО: bind/rebind всегда идут через pending_zone_id.
                     * zone_id подтверждается только после config_report из целевого namespace.
                     */
                    $data['pending_zone_id'] = $newZoneId;

                    /**
                     * Уход с assigned MQTT namespace (cross-zone rebind или recovery с zone_id):
                     * best-effort firmware unbind ДО очистки zone_id — как detach/swap.
                     * Иначе нода остаётся на старом zone-топике и не слышит temp bind-конфиг.
                     * First-bind (zone_id был null) — unbind не нужен.
                     * Same-zone idempotent ASSIGNED — сюда не попадаем.
                     */
                    if ($oldZoneId) {
                        $this->firmwareUnbindService->publishTempNamespaceConfig(
                            $node,
                            (int) $oldZoneId
                        );
                        $this->firmwareUnbindService->mirrorTempNamespaceInStoredConfig($node);
                    }

                    // Если это перепривязка в другую зону, сбрасываем в REGISTERED_BACKEND.
                    if ($oldZoneId && (int) $oldZoneId !== (int) $newZoneId) {
                        $node->zone_id = null; // Явно очищаем старый zone_id
                        $this->transitionLifecycleToRegistered(
                            $node,
                            'reassign_to_another_zone'
                        );
                        $this->clearNodeChannelBindings($node->id, 'reassign_to_another_zone');
                        Log::info('Node re-assignment: reset to REGISTERED_BACKEND, waiting for confirmation', [
                            'node_id' => $node->id,
                            'old_zone_id' => $oldZoneId,
                            'pending_zone_id' => $newZoneId,
                        ]);
                    } else {
                        // Первичная привязка или recovery из неконсистентного состояния.
                        $node->zone_id = null;
                        $this->transitionLifecycleToRegistered(
                            $node,
                            'bind_flow_normalize'
                        );
                    }

                    Log::info('UI zone assignment: set pending_zone_id, waiting for node confirmation', [
                        'node_id' => $node->id,
                        'pending_zone_id' => $newZoneId,
                        'old_zone_id' => $oldZoneId,
                        'lifecycle_state' => $node->lifecycle_state?->value,
                    ]);
                }
            }

            $node->update($data);

            if ($shouldRepublishConfig) {
                DB::afterCommit(function () use ($node) {
                    event(new NodeConfigUpdated($node->fresh()));
                });
            }

            // БАГ #2 FIX: Убрана дублирующая публикация конфига
            // Публикация происходит только через событие NodeConfigUpdated в DeviceNode::saved
            // Это предотвращает двойную публикацию конфига
            // if ($isAssignmentFromUI) {
            //     \App\Jobs\PublishNodeConfigJob::dispatch($node->id);
            // }

            // Логируем завершение bind/rebind после observed config_report.
            if ($isBindingCompletion && $node->zone_id && ! $node->pending_zone_id) {
                Log::info('NodeService: Binding completed in Laravel (zone_id set, pending_zone_id cleared)', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                    'zone_id' => $node->zone_id,
                    'old_zone_id' => $oldZoneId,
                    'old_pending_zone_id' => $oldPendingZoneId,
                    'new_zone_id' => $node->zone_id,
                    'new_pending_zone_id' => $node->pending_zone_id,
                    'lifecycle_state' => $node->lifecycle_state?->value,
                    'reason' => 'Laravel completed node binding after observed config_report',
                ]);

                // Превращаем накопленные unassigned ошибки в alerts теперь, когда зона известна.
                try {
                    $this->registryService->attachUnassignedErrorsForNode($node);
                } catch (\Throwable $e) {
                    Log::error('NodeService: Failed to attach unassigned node errors on binding completion', [
                        'node_id' => $node->id,
                        'uid' => $node->uid,
                        'hardware_id' => $node->hardware_id,
                        'zone_id' => $node->zone_id,
                        'error' => $e->getMessage(),
                    ]);
                }
            }

            /**
             * Если узел отвязан от зоны (zone_id стал null), но НЕ при привязке от UI
             * КРИТИЧНО: Не срабатывает при привязке от UI, так как там pending_zone_id установлен
             */
            if (! $node->zone_id && $oldZoneId && ! $isAssignmentFromUI) {
                $unbindFromZoneId = (int) $oldZoneId;
                $node->pending_zone_id = null; // Очищаем pending_zone_id при отвязке
                $this->firmwareUnbindService->mirrorTempNamespaceInStoredConfig($node);
                $this->transitionLifecycleToRegistered($node, 'zone_cleared_via_update');
                if ($node->isDirty()) {
                    $node->save();
                }
                $this->clearNodeChannelBindings($node->id, 'zone_cleared_via_update');

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
             * Очищаем кеш списка устройств.
             *
             * S2.1 (AUDIT_2026_05_28_BUGFIX_PLAN): без поддержки тегов мы НЕ
             * вызываем `Cache::flush()` (это DoS на shared cache, выбивая
             * сессии, throttle-rate-counters, scheduler state). Очищаем только
             * известные fixed-ключи; per-user ключи `devices_list_<uid>` имеют
             * TTL=2 сек (см. routes/web.php) и сами быстро освежатся.
             */
            $this->invalidateDevicesListCache($node->zone_id);

            return $node->fresh();
        }, maxRetries: 6, baseDelayMs: 75, useSerializable: false);

        // Best-effort firmware unbind после commit (HTTP вне транзакции).
        if ($unbindFromZoneId !== null) {
            $this->firmwareUnbindService->publishTempNamespaceConfig($updated, $unbindFromZoneId);
        }

        return $updated;
    }

    /**
     * Отвязать узел от зоны.
     * При отвязке нода сбрасывается в REGISTERED_BACKEND и считается новой.
     * До очистки БД best-effort публикуется unbind NodeConfig (gh-temp/zn-temp),
     * чтобы firmware ушла из старого MQTT namespace.
     */
    public function detach(DeviceNode $node): DeviceNode
    {
        $oldZoneId = $node->zone_id;
        $oldPendingZoneId = $node->pending_zone_id;

        // Если нода уже отвязана (нет ни zone_id, ни pending_zone_id), ничего не делаем
        if (! $oldZoneId && ! $oldPendingZoneId) {
            Log::info('Node already detached', [
                'node_id' => $node->id,
                'uid' => $node->uid,
            ]);

            return $node;
        }

        // Пока нода ещё assigned — публикуем unbind в текущий zone-топик через HL.
        // Ошибка/offline не блокирует detach: HL дропает zombie telemetry (node_unassigned).
        if ($oldZoneId) {
            $this->firmwareUnbindService->publishTempNamespaceConfig($node, (int) $oldZoneId);
        }

        return DB::transaction(function () use ($node, $oldZoneId, $oldPendingZoneId) {
            // Отвязываем от зоны
            $node->zone_id = null;

            /**
             * КРИТИЧНО: Очищаем pending_zone_id при отвязке
             * Если нода была в процессе привязки (pending_zone_id установлен, но zone_id еще null),
             * необходимо очистить pending_zone_id, чтобы избежать проблем
             */
            $node->pending_zone_id = null;

            // Сбрасываем lifecycle через FSM, чтобы нода снова появилась в пуле для привязки
            $this->firmwareUnbindService->mirrorTempNamespaceInStoredConfig($node);
            $this->transitionLifecycleToRegistered($node, 'explicit_detach');
            if ($node->isDirty()) {
                $node->save();
            }
            $this->clearNodeChannelBindings($node->id, 'explicit_detach');

            Log::info('Node detached from zone', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'old_zone_id' => $oldZoneId,
                'old_pending_zone_id' => $oldPendingZoneId,
                'new_lifecycle_state' => $node->lifecycle_state?->value,
            ]);

            // S2.1: targeted cache invalidation (см. NodeService::update()).
            $this->invalidateDevicesListCache($oldZoneId);

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

    /**
     * Сброс lifecycle в REGISTERED_BACKEND через NodeLifecycleService FSM.
     *
     * Используется при bind/rebind/detach — прямой записи lifecycle_state быть не должно.
     *
     * @throws \DomainException если переход запрещён FSM
     */
    private function transitionLifecycleToRegistered(DeviceNode $node, string $reason): void
    {
        if ($node->lifecycleState() === NodeLifecycleState::REGISTERED_BACKEND) {
            return;
        }

        $previous = $node->lifecycleState()->value;
        $ok = $this->lifecycleService->transitionToRegistered($node, $reason);

        if (! $ok) {
            throw new \DomainException(
                "Cannot reset node lifecycle to REGISTERED_BACKEND from {$previous} ({$reason})"
            );
        }

        Log::info('Node lifecycle normalized to REGISTERED_BACKEND via FSM', [
            'node_id' => $node->id,
            'uid' => $node->uid,
            'previous_lifecycle_state' => $previous,
            'reason' => $reason,
        ]);
    }

    private function clearNodeChannelBindings(int $nodeId, string $reason): void
    {
        try {
            $deleted = DB::table('channel_bindings')
                ->whereIn('node_channel_id', function ($query) use ($nodeId) {
                    $query->select('id')
                        ->from('node_channels')
                        ->where('node_id', $nodeId);
                })
                ->delete();

            if ($deleted > 0) {
                Log::info('NodeService: Cleared channel bindings for node', [
                    'node_id' => $nodeId,
                    'deleted_bindings' => $deleted,
                    'reason' => $reason,
                ]);
            }
        } catch (\Throwable $e) {
            Log::error('NodeService: Failed to clear node channel bindings', [
                'node_id' => $nodeId,
                'reason' => $reason,
                'error' => $e->getMessage(),
            ]);
        }
    }
}
