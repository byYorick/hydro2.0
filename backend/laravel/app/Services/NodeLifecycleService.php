<?php

namespace App\Services;

use App\Enums\NodeLifecycleState;
use App\Models\DeviceNode;
use App\Helpers\TransactionHelper;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class NodeLifecycleService
{
    /**
     * Разрешённые переходы между состояниями.
     * 
     * Ключ - текущее состояние, значение - массив разрешённых целевых состояний.
     */
    private const ALLOWED_TRANSITIONS = [
        NodeLifecycleState::MANUFACTURED->value => [
            NodeLifecycleState::UNPROVISIONED->value,
        ],
        NodeLifecycleState::UNPROVISIONED->value => [
            NodeLifecycleState::PROVISIONED_WIFI->value,
        ],
        NodeLifecycleState::PROVISIONED_WIFI->value => [
            NodeLifecycleState::REGISTERED_BACKEND->value,
            NodeLifecycleState::UNPROVISIONED->value, // Можно сбросить
        ],
        NodeLifecycleState::REGISTERED_BACKEND->value => [
            NodeLifecycleState::ASSIGNED_TO_ZONE->value,
            NodeLifecycleState::DECOMMISSIONED->value,
        ],
        NodeLifecycleState::ASSIGNED_TO_ZONE->value => [
            NodeLifecycleState::ACTIVE->value,
            NodeLifecycleState::MAINTENANCE->value,
            NodeLifecycleState::DECOMMISSIONED->value,
        ],
        NodeLifecycleState::ACTIVE->value => [
            NodeLifecycleState::DEGRADED->value,
            NodeLifecycleState::MAINTENANCE->value,
            NodeLifecycleState::DECOMMISSIONED->value,
        ],
        NodeLifecycleState::DEGRADED->value => [
            NodeLifecycleState::ACTIVE->value,
            NodeLifecycleState::MAINTENANCE->value,
            NodeLifecycleState::DECOMMISSIONED->value,
        ],
        NodeLifecycleState::MAINTENANCE->value => [
            NodeLifecycleState::ACTIVE->value,
            NodeLifecycleState::DEGRADED->value,
            NodeLifecycleState::ASSIGNED_TO_ZONE->value,
            NodeLifecycleState::DECOMMISSIONED->value,
        ],
        NodeLifecycleState::DECOMMISSIONED->value => [
            // DECOMMISSIONED - конечное состояние, переходы обратно невозможны
        ],
    ];

    /**
     * Переход узла в указанное состояние с валидацией.
     * 
     * @param DeviceNode $node
     * @param NodeLifecycleState $targetState
     * @param string|null $reason Причина перехода (для логирования)
     * @return bool Успешно ли выполнен переход
     */
    public function transition(
        DeviceNode $node,
        NodeLifecycleState $targetState,
        ?string $reason = null
    ): bool {
        // Используем SERIALIZABLE isolation level для критичной операции перехода состояния
        return TransactionHelper::withSerializableRetry(function () use ($node, $targetState, $reason) {
            $currentState = $node->lifecycleState();
            $targetValue = $targetState->value;

            // Проверяем, разрешён ли переход
            if (!$this->isTransitionAllowed($currentState, $targetState)) {
                Log::warning('Node lifecycle transition not allowed', [
                    'node_id' => $node->id,
                    'node_uid' => $node->uid,
                    'current_state' => $currentState->value,
                    'target_state' => $targetValue,
                    'reason' => $reason,
                ]);
                return false;
            }

            // Обновляем состояние
            $node->lifecycle_state = $targetState;
            
            // Дополнительные действия в зависимости от целевого состояния
            match ($targetState) {
                NodeLifecycleState::ACTIVE => $node->status = 'online',
                NodeLifecycleState::DEGRADED => $node->status = 'online', // Деградированный узел всё ещё online
                NodeLifecycleState::MAINTENANCE => $node->status = 'offline',
                NodeLifecycleState::DECOMMISSIONED => $node->status = 'offline',
                default => null,
            };

            $node->save();

            Log::info('Node lifecycle transition', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'from_state' => $currentState->value,
                'to_state' => $targetValue,
                'reason' => $reason,
            ]);

            return true;
        });
    }

    /**
     * Проверить, разрешён ли переход между состояниями.
     */
    public function isTransitionAllowed(
        NodeLifecycleState $current,
        NodeLifecycleState $target
    ): bool {
        // Переход в то же самое состояние всегда разрешён
        if ($current === $target) {
            return true;
        }

        $allowedTargets = self::ALLOWED_TRANSITIONS[$current->value] ?? [];
        return in_array($target->value, $allowedTargets, true);
    }

    /**
     * Переход в состояние PROVISIONED_WIFI.
     */
    public function transitionToProvisioned(DeviceNode $node, ?string $reason = null): bool
    {
        return $this->transition($node, NodeLifecycleState::PROVISIONED_WIFI, $reason);
    }

    /**
     * Переход в состояние REGISTERED_BACKEND.
     */
    public function transitionToRegistered(DeviceNode $node, ?string $reason = null): bool
    {
        return $this->transition($node, NodeLifecycleState::REGISTERED_BACKEND, $reason);
    }

    /**
     * Переход в состояние ASSIGNED_TO_ZONE.
     */
    public function transitionToAssigned(DeviceNode $node, ?string $reason = null): bool
    {
        return $this->transition($node, NodeLifecycleState::ASSIGNED_TO_ZONE, $reason);
    }

    /**
     * Переход в состояние ACTIVE.
     */
    public function transitionToActive(DeviceNode $node, ?string $reason = null): bool
    {
        return $this->transition($node, NodeLifecycleState::ACTIVE, $reason);
    }

    /**
     * Переход в состояние DEGRADED.
     */
    public function transitionToDegraded(DeviceNode $node, ?string $reason = null): bool
    {
        return $this->transition($node, NodeLifecycleState::DEGRADED, $reason);
    }

    /**
     * Переход в состояние MAINTENANCE.
     */
    public function transitionToMaintenance(DeviceNode $node, ?string $reason = null): bool
    {
        return $this->transition($node, NodeLifecycleState::MAINTENANCE, $reason);
    }

    /**
     * Переход в состояние DECOMMISSIONED.
     */
    public function transitionToDecommissioned(DeviceNode $node, ?string $reason = null): bool
    {
        return $this->transition($node, NodeLifecycleState::DECOMMISSIONED, $reason);
    }
}

