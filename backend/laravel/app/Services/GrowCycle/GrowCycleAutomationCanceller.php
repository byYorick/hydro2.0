<?php

declare(strict_types=1);

namespace App\Services\GrowCycle;

use App\Models\GrowCycle;
use App\Models\Zone;
use Carbon\Carbon;
use Illuminate\Support\Facades\DB;

/**
 * Отменяет активные intents и ae_tasks зоны при завершении цикла или смене фазы.
 *
 * AE3 worker owns the lease lifecycle — cancel помечает task/intent как cancelled
 * и полагается на finally-path worker'а для освобождения lease.
 */
class GrowCycleAutomationCanceller
{
    public function __construct(
        private readonly GrowCycleAutomationDispatcher $dispatcher,
    ) {}

    /**
     * Отменяет cycle_start runtime state (intent + ae_task) для конкретного цикла.
     * Не трогает IRRIGATE_ONCE / LIGHTING_TICK intents — для них используется
     * {@see cancelAllZoneAutomationState}.
     */
    public function cancelGrowCycleStartRuntimeState(
        GrowCycle $cycle,
        Zone $zone,
        string $errorCode = 'grow_cycle_aborted',
        ?string $errorMessage = null,
    ): void {
        if (strtolower(trim((string) $zone->automation_runtime)) !== 'ae3') {
            return;
        }

        $zoneId = (int) $cycle->zone_id;
        $cycleId = (int) $cycle->id;
        if ($zoneId <= 0 || $cycleId <= 0) {
            return;
        }

        $idempotencyKey = $this->dispatcher->buildIdempotencyKey($zoneId, $cycleId);
        $now = Carbon::now('UTC')->setMicroseconds(0);
        $errorMessage ??= sprintf(
            'Grow cycle %d cancelled before AE3 start-cycle task completed',
            $cycleId
        );

        DB::table('zone_automation_intents')
            ->where('zone_id', $zoneId)
            ->whereIn('status', ['pending', 'claimed', 'running'])
            ->where(function ($query) use ($idempotencyKey, $cycleId) {
                $query->where('idempotency_key', $idempotencyKey)
                    ->orWhere(function ($cycleQuery) use ($cycleId) {
                        $cycleQuery
                            ->where('intent_type', 'DIAGNOSTICS_TICK')
                            ->where('task_type', 'cycle_start')
                            ->whereRaw(
                                "COALESCE(NULLIF(payload->>'grow_cycle_id', ''), '0')::bigint = ?",
                                [$cycleId]
                            );
                    });
            })
            ->update([
                'status' => 'cancelled',
                'completed_at' => $now,
                'updated_at' => $now,
                'error_code' => $errorCode,
                'error_message' => $errorMessage,
            ]);

        DB::table('ae_tasks')
            ->where('zone_id', $zoneId)
            ->whereIn('status', ['pending', 'claimed', 'running', 'waiting_command'])
            ->where(function ($query) use ($idempotencyKey, $cycleId) {
                $query->where('idempotency_key', $idempotencyKey)
                    ->orWhere(function ($cycleQuery) use ($cycleId) {
                        $cycleQuery
                            ->where('task_type', 'cycle_start')
                            ->whereRaw(
                                "COALESCE(NULLIF(intent_meta->'intent_payload'->>'grow_cycle_id', ''), '0')::bigint = ?",
                                [$cycleId]
                            );
                    });
            })
            ->update([
                'status' => 'cancelled',
                'completed_at' => $now,
                'updated_at' => $now,
                'error_code' => $errorCode,
                'error_message' => $errorMessage,
            ]);
    }

    /**
     * Отменяет ВСЕ активные pending/claimed/running intents и ae_tasks зоны.
     * Вызывается при harvest/abort цикла, чтобы не оставить orphaned irrigation/
     * lighting intents и tasks после завершения цикла.
     */
    public function cancelAllZoneAutomationState(
        GrowCycle $cycle,
        Zone $zone,
        string $errorCode,
        ?string $errorMessage = null,
    ): void {
        if (strtolower(trim((string) $zone->automation_runtime)) !== 'ae3') {
            return;
        }

        $zoneId = (int) $zone->id;
        $cycleId = (int) $cycle->id;
        if ($zoneId <= 0) {
            return;
        }

        $now = Carbon::now('UTC')->setMicroseconds(0);
        $errorMessage ??= sprintf(
            'Grow cycle %d ended — cancelling remaining zone automation state',
            $cycleId
        );

        DB::table('zone_automation_intents')
            ->where('zone_id', $zoneId)
            ->whereIn('status', ['pending', 'claimed', 'running'])
            ->update([
                'status' => 'cancelled',
                'completed_at' => $now,
                'updated_at' => $now,
                'error_code' => $errorCode,
                'error_message' => $errorMessage,
            ]);

        DB::table('ae_tasks')
            ->where('zone_id', $zoneId)
            ->whereIn('status', ['pending', 'claimed', 'running', 'waiting_command'])
            ->update([
                'status' => 'cancelled',
                'completed_at' => $now,
                'updated_at' => $now,
                'error_code' => $errorCode,
                'error_message' => $errorMessage,
            ]);
    }

    /**
     * Отменяет pending (undispatched) scheduler-intents зоны при смене фазы.
     * IRRIGATE_ONCE / LIGHTING_TICK с параметрами предыдущей фазы
     * не должны превращаться в AE3 tasks после advancePhase.
     */
    public function cancelStalePendingIntentsOnPhaseAdvance(int $zoneId): void
    {
        if ($zoneId <= 0) {
            return;
        }
        $now = Carbon::now('UTC')->setMicroseconds(0);
        DB::table('zone_automation_intents')
            ->where('zone_id', $zoneId)
            ->where('status', 'pending')
            ->whereIn('intent_type', ['IRRIGATE_ONCE', 'LIGHTING_TICK'])
            ->update([
                'status' => 'cancelled',
                'completed_at' => $now,
                'updated_at' => $now,
                'error_code' => 'phase_advanced_before_dispatch',
                'error_message' => 'Intent from previous phase cancelled because cycle advanced to next phase before dispatch',
            ]);
    }
}
