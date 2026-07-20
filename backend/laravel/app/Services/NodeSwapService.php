<?php

namespace App\Services;

use App\Enums\NodeLifecycleState;
use App\Models\DeviceNode;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class NodeSwapService
{
    public function __construct(
        private readonly ZoneNodeAutomationBindingValidator $bindingValidator,
        private readonly NodeLifecycleService $lifecycleService,
        private readonly NodeFirmwareUnbindService $firmwareUnbindService,
        private readonly NodeSecretService $nodeSecretService,
    ) {}

    /**
     * Заменить узел новым узлом через pending bind-контракт.
     *
     * Новый узел получает pending_zone_id (zone_id остаётся null) до config_report.
     * Старый узел снимается с зоны и переводится в DECOMMISSIONED.
     * До очистки zone_id — best-effort firmware unbind (NodeConfig gh-temp/zn-temp),
     * по аналогии с NodeService::detach().
     *
     * @param  array{
     *     migrate_telemetry?: bool,
     *     migrate_channels?: bool
     * }  $options
     */
    public function swapNode(int $oldNodeId, string $newHardwareId, array $options = []): DeviceNode
    {
        // Best-effort unbind до транзакции: HTTP вне DB lock, пока нода ещё на zone-топике.
        $oldPreview = DeviceNode::query()->findOrFail($oldNodeId);
        $unbindZoneId = $oldPreview->zone_id;
        if ($unbindZoneId) {
            $this->firmwareUnbindService->publishTempNamespaceConfig($oldPreview, (int) $unbindZoneId);
        }

        return DB::transaction(function () use ($oldNodeId, $newHardwareId, $options) {
            $oldNode = DeviceNode::query()->lockForUpdate()->findOrFail($oldNodeId);
            $targetZoneId = $oldNode->zone_id ?? $oldNode->pending_zone_id;

            if (! $targetZoneId) {
                throw new \DomainException(
                    'Cannot swap node that is not assigned or pending assignment to a zone'
                );
            }

            if ($oldNode->lifecycleState() === NodeLifecycleState::DECOMMISSIONED) {
                throw new \DomainException('Cannot swap a decommissioned node');
            }

            $newNode = DeviceNode::query()
                ->where('hardware_id', $newHardwareId)
                ->lockForUpdate()
                ->first();

            if ($newNode && (int) $newNode->id === (int) $oldNode->id) {
                throw new \DomainException('Cannot swap a node with itself');
            }

            if ($newNode) {
                $this->assertNewNodeEligibleForSwap($newNode, (int) $targetZoneId);
            }

            // Сначала освобождаем зону у старого узла — иначе fail-closed validator
            // увидит дубликат роли/телеметрии на той же зоне.
            $this->firmwareUnbindService->mirrorTempNamespaceInStoredConfig($oldNode);
            $oldNode->zone_id = null;
            $oldNode->pending_zone_id = null;
            $oldNode->save();

            if (! $this->lifecycleService->transitionToDecommissioned($oldNode, 'node_swap')) {
                throw new \DomainException(
                    'Cannot decommission old node: lifecycle transition not allowed from '.$oldNode->lifecycleState()->value
                );
            }

            if (! $newNode) {
                $newNode = new DeviceNode;
                $newNode->uid = $this->generateNewNodeUid($oldNode);
                $newNode->hardware_id = $newHardwareId;
                $newNode->type = $oldNode->type;
                $newNode->name = $oldNode->name.' (заменён)';
                $newNode->validated = true;
                $newNode->first_seen_at = now();
                $newNode->zone_id = null;
                $newNode->pending_zone_id = null;
                $newNode->status = 'offline';
                $this->nodeSecretService->ensureOnNode($newNode);
                $newNode->save();

                if (! $this->lifecycleService->ensureRegistered($newNode, 'node_swap_create')) {
                    throw new \DomainException(
                        'Cannot register replacement node: lifecycle transition to REGISTERED_BACKEND failed'
                    );
                }

                Log::info('New node created during swap', [
                    'old_node_id' => $oldNodeId,
                    'new_node_id' => $newNode->id,
                    'new_hardware_id' => $newHardwareId,
                ]);
            } else {
                if (! $this->lifecycleService->ensureRegistered($newNode, 'node_swap_reuse')) {
                    throw new \DomainException(
                        'Cannot prepare replacement node: lifecycle transition to REGISTERED_BACKEND failed'
                    );
                }
                $this->nodeSecretService->ensureOnNode($newNode);
            }

            $migrateChannels = $options['migrate_channels'] ?? true;
            if ($migrateChannels) {
                $oldNode->channels()->update(['node_id' => $newNode->id]);
                Log::info('Channels migrated to new node', [
                    'old_node_id' => $oldNodeId,
                    'new_node_id' => $newNode->id,
                ]);
            }

            $this->bindingValidator->assertBindAllowed($newNode, (int) $targetZoneId);

            $newNode->zone_id = null;
            $newNode->pending_zone_id = (int) $targetZoneId;
            $newNode->save();

            $migrateTelemetry = $options['migrate_telemetry'] ?? false;
            $telemetryMigrationResult = null;
            if ($migrateTelemetry) {
                $telemetryMigrationResult = $this->migrateTelemetryHistory($oldNode->id, $newNode->id);
                if (! $telemetryMigrationResult['success']) {
                    throw new \DomainException(
                        'Telemetry migration failed: '.($telemetryMigrationResult['error'] ?? 'Unknown error')
                    );
                }
            }

            Log::info('Node swap completed (pending bind)', [
                'old_node_id' => $oldNodeId,
                'old_uid' => $oldNode->uid,
                'new_node_id' => $newNode->id,
                'new_uid' => $newNode->uid,
                'new_hardware_id' => $newHardwareId,
                'pending_zone_id' => $newNode->pending_zone_id,
                'zone_id' => $newNode->zone_id,
                'telemetry_migrated' => $migrateTelemetry,
                'telemetry_migration_success' => $telemetryMigrationResult['success'] ?? null,
            ]);

            $fresh = $newNode->fresh();
            $fresh->setAttribute('_swap_metadata', [
                'telemetry_migrated' => $migrateTelemetry,
                'telemetry_migration_success' => $telemetryMigrationResult['success'] ?? null,
                'telemetry_migration_warning' => $telemetryMigrationResult['warning'] ?? null,
                'pending_bind' => true,
                'pending_zone_id' => $fresh->pending_zone_id,
            ]);

            return $fresh;
        });
    }

    private function assertNewNodeEligibleForSwap(DeviceNode $newNode, int $targetZoneId): void
    {
        if ($newNode->lifecycleState() === NodeLifecycleState::DECOMMISSIONED) {
            throw new \DomainException('Cannot swap onto a decommissioned node');
        }

        if ($newNode->zone_id && (int) $newNode->zone_id !== $targetZoneId) {
            throw new \DomainException(
                'Replacement node is already assigned to another zone'
            );
        }

        if (
            $newNode->pending_zone_id
            && (int) $newNode->pending_zone_id !== $targetZoneId
            && ! $newNode->zone_id
        ) {
            throw new \DomainException(
                'Replacement node already has a pending bind to another zone'
            );
        }

        if ($newNode->zone_id && (int) $newNode->zone_id === $targetZoneId) {
            throw new \DomainException(
                'Replacement node is already assigned to the target zone; finalize or detach first'
            );
        }
    }

    /**
     * @return array{success: bool, error: ?string, warning: ?string, samples_migrated?: int, last_migrated?: int, sensors_migrated?: int}
     */
    private function migrateTelemetryHistory(int $oldNodeId, int $newNodeId): array
    {
        try {
            $sensorIds = DB::table('sensors')
                ->where('node_id', $oldNodeId)
                ->pluck('id');

            $sensorsCount = $sensorIds->count();
            $samplesCount = $sensorIds->isEmpty()
                ? 0
                : DB::table('telemetry_samples')->whereIn('sensor_id', $sensorIds)->count();
            $lastCount = $sensorIds->isEmpty()
                ? 0
                : DB::table('telemetry_last')->whereIn('sensor_id', $sensorIds)->count();

            $sensorsUpdated = DB::table('sensors')
                ->where('node_id', $oldNodeId)
                ->update(['node_id' => $newNodeId]);

            $warning = null;
            if ($sensorsUpdated !== $sensorsCount) {
                $warning = "Expected to migrate {$sensorsCount} sensors, but only {$sensorsUpdated} were updated.";
                Log::warning('Telemetry migration: sensors count mismatch', [
                    'old_node_id' => $oldNodeId,
                    'new_node_id' => $newNodeId,
                    'expected' => $sensorsCount,
                    'updated' => $sensorsUpdated,
                ]);
            }

            Log::info('Telemetry history migrated', [
                'old_node_id' => $oldNodeId,
                'new_node_id' => $newNodeId,
                'sensors_migrated' => $sensorsUpdated,
                'samples_affected' => $samplesCount,
                'last_affected' => $lastCount,
            ]);

            return [
                'success' => true,
                'error' => null,
                'warning' => $warning,
                'samples_migrated' => $samplesCount,
                'last_migrated' => $lastCount,
                'sensors_migrated' => $sensorsUpdated,
            ];
        } catch (\Exception $e) {
            Log::error('Failed to migrate telemetry history', [
                'old_node_id' => $oldNodeId,
                'new_node_id' => $newNodeId,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
                'trace' => $e->getTraceAsString(),
            ]);

            return [
                'success' => false,
                'error' => $e->getMessage(),
                'warning' => null,
            ];
        }
    }

    private function generateNewNodeUid(DeviceNode $oldNode): string
    {
        $baseUid = $oldNode->uid;
        $counter = 1;

        do {
            $newUid = $baseUid."-swap{$counter}";
            $exists = DeviceNode::where('uid', $newUid)->exists();
            $counter++;
        } while ($exists && $counter < 100);

        return $newUid;
    }
}
