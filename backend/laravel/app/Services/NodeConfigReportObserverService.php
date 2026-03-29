<?php

namespace App\Services;

use App\Models\DeviceNode;
use Illuminate\Support\Facades\Log;

class NodeConfigReportObserverService
{
    public function __construct(
        private readonly NodeService $nodeService,
        private readonly NodeLifecycleService $nodeLifecycleService,
    ) {
    }

    /**
     * Laravel-only owner of bind/rebind completion after observed config_report.
     *
     * @param  array<string, mixed>  $observed
     * @return array<string, mixed>
     */
    public function observe(DeviceNode $node, array $observed): array
    {
        $node = $node->fresh();
        if (! $node) {
            return [
                'finalized' => false,
                'reason' => 'node_not_found',
            ];
        }

        if ((bool) ($observed['is_temp_topic'] ?? false)) {
            return [
                'finalized' => false,
                'reason' => 'temp_topic',
            ];
        }

        if ($node->zone_id || ! $node->pending_zone_id) {
            return [
                'finalized' => false,
                'reason' => 'no_pending_binding',
                'zone_id' => $node->zone_id,
                'pending_zone_id' => $node->pending_zone_id,
            ];
        }

        $targetZone = \App\Models\Zone::with('greenhouse')->find($node->pending_zone_id);
        if (! $targetZone) {
            Log::warning('NodeConfigReportObserverService: Pending bind target zone not found', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'pending_zone_id' => $node->pending_zone_id,
            ]);

            return [
                'finalized' => false,
                'reason' => 'target_zone_missing',
                'pending_zone_id' => $node->pending_zone_id,
            ];
        }

        $observedGhUid = trim((string) ($observed['gh_uid'] ?? ''));
        $observedZoneUid = trim((string) ($observed['zone_uid'] ?? ''));
        $targetGhUid = trim((string) ($targetZone->greenhouse?->uid ?? ''));
        $targetZoneUid = trim((string) ($targetZone->uid ?? ''));

        if (
            $observedGhUid === ''
            || $observedZoneUid === ''
            || $observedGhUid !== $targetGhUid
            || $observedZoneUid !== $targetZoneUid
        ) {
            Log::info('NodeConfigReportObserverService: Deferred bind completion due to namespace mismatch', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'pending_zone_id' => $node->pending_zone_id,
                'observed_gh_uid' => $observedGhUid ?: null,
                'observed_zone_uid' => $observedZoneUid ?: null,
                'target_gh_uid' => $targetGhUid,
                'target_zone_uid' => $targetZoneUid,
            ]);

            return [
                'finalized' => false,
                'reason' => 'namespace_mismatch',
                'pending_zone_id' => $node->pending_zone_id,
            ];
        }

        $updatedNode = $this->nodeService->update($node, [
            'zone_id' => $node->pending_zone_id,
            'pending_zone_id' => null,
        ]);

        $transitioned = $this->nodeLifecycleService->transitionToAssigned(
            $updatedNode,
            'Config report observed by Laravel'
        );

        if (! $transitioned) {
            Log::warning('NodeConfigReportObserverService: Bind finalized but ASSIGNED_TO_ZONE transition denied', [
                'node_id' => $updatedNode->id,
                'uid' => $updatedNode->uid,
                'zone_id' => $updatedNode->zone_id,
                'lifecycle_state' => $updatedNode->lifecycle_state?->value,
            ]);
        }

        return [
            'finalized' => true,
            'transitioned' => $transitioned,
            'zone_id' => $updatedNode->fresh()?->zone_id,
        ];
    }
}
