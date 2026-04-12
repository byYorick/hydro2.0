<?php

namespace App\Services;

use Carbon\CarbonImmutable;
use Illuminate\Support\Arr;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class ZoneAutomationIntentService
{
    public function __construct(
        private readonly AutomationConfigDocumentService $documents,
        private readonly ZoneLogicProfileService $logicProfiles,
    ) {
    }

    /**
     * Топология для AE3 intent (resolved из zone logic profile).
     */
    public function resolveAe3TopologyForZone(int $zoneId): string
    {
        try {
            $profile = $this->logicProfiles->resolveActiveProfileForZone($zoneId);
            $subsystems = $profile?->subsystems ?? [];
            $topology = Arr::get($subsystems, 'diagnostics.execution.topology');
            if (is_string($topology) && trim($topology) !== '') {
                return strtolower(trim($topology));
            }
        } catch (\Throwable $e) {
            Log::debug('Could not resolve AE3 topology from zone logic profile', [
                'zone_id' => $zoneId,
                'error' => $e->getMessage(),
            ]);
        }

        return 'two_tank_drip_substrate_trays';
    }

    public function upsertStartIrrigationIntent(
        int $zoneId,
        string $source,
        string $idempotencyKey,
        string $mode,
        ?int $requestedDurationSec = null,
    ): ?int {
        $this->documents->ensureZoneDefaults($zoneId);

        $now = CarbonImmutable::now('UTC')->setMicroseconds(0);
        $intentSource = trim($source) !== '' ? trim($source) : 'laravel_api';
        $irrigationMode = $mode === 'force' ? 'force' : 'normal';
        $topology = $this->resolveAe3TopologyForZone($zoneId);
        $durationSec = $requestedDurationSec !== null ? max(1, $requestedDurationSec) : null;

        $row = DB::selectOne(
            "
            INSERT INTO zone_automation_intents (
                zone_id,
                intent_type,
                task_type,
                topology,
                irrigation_mode,
                irrigation_requested_duration_sec,
                intent_source,
                idempotency_key,
                status,
                not_before,
                retry_count,
                max_retries,
                created_at,
                updated_at
            )
            VALUES (?, 'IRRIGATE_ONCE', 'irrigation_start', ?, ?, ?, ?, ?, 'pending', ?, 0, 3, ?, ?)
            ON CONFLICT (zone_id, idempotency_key)
            DO UPDATE SET
                task_type = EXCLUDED.task_type,
                topology = EXCLUDED.topology,
                irrigation_mode = EXCLUDED.irrigation_mode,
                irrigation_requested_duration_sec = EXCLUDED.irrigation_requested_duration_sec,
                intent_source = EXCLUDED.intent_source,
                not_before = EXCLUDED.not_before,
                updated_at = EXCLUDED.updated_at
            WHERE zone_automation_intents.status NOT IN ('completed', 'failed', 'cancelled')
            RETURNING id
            ",
            [
                $zoneId,
                $topology,
                $irrigationMode,
                $durationSec,
                $intentSource,
                $idempotencyKey,
                $now,
                $now,
                $now,
            ],
        );

        $intentId = isset($row->id) ? (int) $row->id : null;

        Log::info('Start irrigation intent upserted', [
            'zone_id' => $zoneId,
            'idempotency_key' => $idempotencyKey,
            'intent_id' => $intentId,
            'mode' => $irrigationMode,
            'source' => $intentSource,
        ]);

        return $intentId;
    }

    public function markIntentFailed(
        int $zoneId,
        string $idempotencyKey,
        string $errorCode,
        ?string $errorMessage = null,
    ): void {
        $now = CarbonImmutable::now('UTC')->setMicroseconds(0);

        DB::table('zone_automation_intents')
            ->where('zone_id', $zoneId)
            ->where('idempotency_key', $idempotencyKey)
            ->whereIn('status', ['pending', 'claimed', 'running'])
            ->update([
                'status' => 'failed',
                'completed_at' => $now,
                'updated_at' => $now,
                'error_code' => $errorCode,
                'error_message' => $errorMessage,
            ]);
    }
}
