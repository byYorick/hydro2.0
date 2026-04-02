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
     * Топология для AE3 intent payload (обязательна для LegacyIntentMapper).
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
        $intentPayload = [
            'source' => trim($source) !== '' ? trim($source) : 'laravel_api',
            'task_type' => 'irrigation_start',
            'workflow' => 'irrigation_start',
            'mode' => $mode === 'force' ? 'force' : 'normal',
            'topology' => $this->resolveAe3TopologyForZone($zoneId),
        ];
        if ($requestedDurationSec !== null) {
            $intentPayload['requested_duration_sec'] = max(1, $requestedDurationSec);
        }

        $row = DB::selectOne(
            "
            INSERT INTO zone_automation_intents (
                zone_id,
                intent_type,
                payload,
                idempotency_key,
                status,
                not_before,
                retry_count,
                max_retries,
                created_at,
                updated_at
            )
            VALUES (?, 'IRRIGATE_ONCE', ?::jsonb, ?, 'pending', ?, 0, 3, ?, ?)
            ON CONFLICT (zone_id, idempotency_key)
            DO UPDATE SET
                payload = EXCLUDED.payload,
                not_before = EXCLUDED.not_before,
                updated_at = EXCLUDED.updated_at
            WHERE zone_automation_intents.status NOT IN ('completed', 'failed', 'cancelled')
            RETURNING id
            ",
            [
                $zoneId,
                json_encode($intentPayload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
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
            'mode' => $intentPayload['mode'],
            'source' => $intentPayload['source'],
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
