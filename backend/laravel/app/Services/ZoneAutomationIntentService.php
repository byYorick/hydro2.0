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
    ) {}

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

    public function upsertStartCycleIntent(
        int $zoneId,
        string $source,
        string $idempotencyKey,
    ): ?int {
        $this->documents->ensureZoneDefaults($zoneId);

        $now = CarbonImmutable::now('UTC')->setMicroseconds(0);
        $intentSource = trim($source) !== '' ? trim($source) : 'laravel_api';
        $topology = $this->resolveAe3TopologyForZone($zoneId);

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
            VALUES (?, 'DIAGNOSTICS_TICK', 'cycle_start', ?, NULL, NULL, ?, ?, 'pending', ?, 0, 3, ?, ?)
            ON CONFLICT (zone_id, idempotency_key)
            DO UPDATE SET
                task_type = EXCLUDED.task_type,
                topology = EXCLUDED.topology,
                intent_source = EXCLUDED.intent_source,
                not_before = EXCLUDED.not_before,
                updated_at = EXCLUDED.updated_at
            WHERE zone_automation_intents.status NOT IN ('completed', 'failed', 'cancelled')
            RETURNING id
            ",
            [
                $zoneId,
                $topology,
                $intentSource,
                $idempotencyKey,
                $now,
                $now,
                $now,
            ],
        );

        $intentId = isset($row->id) ? (int) $row->id : null;

        Log::info('Start cycle intent upserted', [
            'zone_id' => $zoneId,
            'idempotency_key' => $idempotencyKey,
            'intent_id' => $intentId,
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

    /**
     * Учитывает retryable dispatch failure планировщика: инкремент retry_count и terminal fail
     * после исчерпания max_retries.
     *
     * @return array{failed: bool, retry_count: int}
     */
    public function recordSchedulerDispatchFailure(
        int $zoneId,
        string $idempotencyKey,
        string $errorCode,
        ?string $errorMessage = null,
    ): array {
        $now = CarbonImmutable::now('UTC')->setMicroseconds(0);

        $row = DB::selectOne(
            "
            UPDATE zone_automation_intents
            SET retry_count = retry_count + 1,
                updated_at = ?
            WHERE zone_id = ?
              AND idempotency_key = ?
              AND intent_source = 'laravel_scheduler'
              AND status IN ('pending', 'claimed', 'running')
            RETURNING retry_count, max_retries
            ",
            [$now, $zoneId, $idempotencyKey],
        );

        if ($row === null) {
            return ['failed' => false, 'retry_count' => 0];
        }

        $retryCount = (int) ($row->retry_count ?? 0);
        $maxRetries = max(1, (int) ($row->max_retries ?? 3));

        if ($retryCount >= $maxRetries) {
            $this->markIntentFailed(
                zoneId: $zoneId,
                idempotencyKey: $idempotencyKey,
                errorCode: $errorCode,
                errorMessage: $errorMessage,
            );

            return ['failed' => true, 'retry_count' => $retryCount];
        }

        return ['failed' => false, 'retry_count' => $retryCount];
    }

    /**
     * Синхронизирует terminal failure intent-а с уже failed ae_task (по idempotency_key).
     */
    public function syncIntentFailedFromAeTask(
        int $zoneId,
        string $idempotencyKey,
        string $errorCode,
        ?string $errorMessage = null,
    ): void {
        if (trim($idempotencyKey) === '') {
            return;
        }

        $transientCodes = [
            'ae3_required_node_offline',
            'command_send_failed',
            'irr_state_unavailable',
            'irr_state_stale',
            'command_timeout',
        ];
        $normalizedCode = strtolower(trim($errorCode));

        if (in_array($normalizedCode, $transientCodes, true)) {
            $taskAlreadyFailed = DB::table('ae_tasks')
                ->where('zone_id', $zoneId)
                ->where('idempotency_key', $idempotencyKey)
                ->where('status', 'failed')
                ->exists();

            if ($taskAlreadyFailed) {
                // Terminal ae_task: повторный dispatch по тому же ключу не произойдёт — не оставляем orphan pending.
            } else {
            $requeued = DB::update(
                "
                UPDATE zone_automation_intents
                SET status = 'pending',
                    retry_count = retry_count + 1,
                    completed_at = NULL,
                    updated_at = ?,
                    not_before = ?,
                    error_code = ?,
                    error_message = ?
                WHERE zone_id = ?
                  AND idempotency_key = ?
                  AND status IN ('pending', 'claimed', 'running')
                  AND retry_count + 1 < max_retries
                ",
                [
                    CarbonImmutable::now('UTC')->setMicroseconds(0),
                    CarbonImmutable::now('UTC')->setMicroseconds(0)->addSeconds(60),
                    $errorCode,
                    $errorMessage,
                    $zoneId,
                    $idempotencyKey,
                ],
            );

            if ($requeued > 0) {
                return;
            }
            }
        }

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
