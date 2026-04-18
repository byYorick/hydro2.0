<?php

declare(strict_types=1);

namespace App\Services\GrowCycle;

use App\Enums\GrowCycleStatus;
use App\Events\GrowCycleUpdated;
use App\Events\ZoneUpdated;
use App\Models\GrowCycle;
use App\Models\GrowCyclePhase;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Services\AutomationConfigCompiler;
use App\Services\AutomationConfigRegistry;
use App\Services\GrowCycle\Support\CorrelationIdResolver;
use App\Services\ZoneService;
use Carbon\Carbon;
use Illuminate\Contracts\Pagination\LengthAwarePaginator;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Управляет lifecycle состояниями grow cycle: start / pause / resume / harvest / abort.
 * Также содержит query-методы (getByGreenhouse) — read paths тонкие.
 */
class GrowCycleLifecycleService
{
    public function __construct(
        private readonly AutomationConfigCompiler $automationConfigCompiler,
        private readonly ZoneService $zoneService,
        private readonly GrowCycleStageTimelineService $timeline,
        private readonly GrowCycleAutomationDispatcher $dispatcher,
        private readonly GrowCycleAutomationCanceller $canceller,
        private readonly CorrelationIdResolver $correlation,
    ) {}

    public function startCycle(GrowCycle $cycle, ?Carbon $plantingAt = null): GrowCycle
    {
        if ($cycle->status !== GrowCycleStatus::PLANNED) {
            throw new \DomainException('Cycle must be in PLANNED status to start');
        }

        $zone = $cycle->zone ?? Zone::query()->find($cycle->zone_id);
        if ($zone) {
            $this->zoneService->ensureAe3AutomationBootstrap($zone);
            if (strtolower(trim((string) ($zone->automation_runtime ?? ''))) === 'ae3') {
                $this->automationConfigCompiler->compileGrowCycleBundle((int) $cycle->id);
            }
        }

        $startedCycle = DB::transaction(function () use ($cycle, $plantingAt) {
            $plantingAt = $plantingAt ?? now();
            $plantingAt->setMicrosecond(0);

            if ($cycle->current_phase_id) {
                $currentPhase = GrowCyclePhase::find($cycle->current_phase_id);
                if ($currentPhase) {
                    $currentPhase->update(['started_at' => $plantingAt]);
                }
            }

            $cycle->update([
                'status' => GrowCycleStatus::RUNNING,
                'planting_at' => $plantingAt,
                'started_at' => $plantingAt,
                'recipe_started_at' => $plantingAt,
                'phase_started_at' => $plantingAt,
            ]);
            $this->syncZoneStatus($cycle->zone, 'RUNNING');
            $this->timeline->computeExpectedHarvest($cycle);

            $zone = $cycle->zone;
            if ($zone) {
                ZoneEvent::create([
                    'zone_id' => $zone->id,
                    'type' => 'CYCLE_STARTED',
                    'entity_type' => 'grow_cycle',
                    'entity_id' => (string) $cycle->id,
                    'payload_json' => [
                        'cycle_id' => $cycle->id,
                        'recipe_revision_id' => $cycle->recipe_revision_id,
                        'current_phase_id' => $cycle->current_phase_id,
                        'planting_at' => $plantingAt->toIso8601String(),
                        'source' => 'backend',
                        'correlation_id' => $this->correlation->resolve(),
                    ],
                ]);
            }

            Log::info('Grow cycle started', [
                'cycle_id' => $cycle->id,
                'planting_at' => $plantingAt,
            ]);

            return $cycle->fresh();
        });

        $this->dispatcher->dispatchAutomationStartCycle($startedCycle);

        return $startedCycle->fresh();
    }

    public function pause(GrowCycle $cycle, int $userId): GrowCycle
    {
        if ($cycle->status !== GrowCycleStatus::RUNNING) {
            throw new \DomainException('Cycle is not running');
        }

        return DB::transaction(function () use ($cycle, $userId) {
            $cycle->update(['status' => GrowCycleStatus::PAUSED]);
            $cycle->refresh();

            $zone = $cycle->zone;
            $this->syncZoneStatus($zone, 'PAUSED');

            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'CYCLE_PAUSED',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $cycle->id,
                'payload_json' => [
                    'cycle_id' => $cycle->id,
                    'user_id' => $userId,
                    'source' => 'web',
                    'correlation_id' => $this->correlation->resolve(),
                ],
            ]);

            broadcast(new GrowCycleUpdated($cycle, 'PAUSED'));

            Log::info('Grow cycle paused', [
                'zone_id' => $zone->id,
                'cycle_id' => $cycle->id,
                'user_id' => $userId,
            ]);

            return $cycle->fresh();
        });
    }

    public function resume(GrowCycle $cycle, int $userId): GrowCycle
    {
        if ($cycle->status !== GrowCycleStatus::PAUSED) {
            throw new \DomainException('Cycle is not paused');
        }

        return DB::transaction(function () use ($cycle, $userId) {
            $cycle->update(['status' => GrowCycleStatus::RUNNING]);
            $cycle->refresh();

            // Пересчёт effective bundle: за время pause мог измениться PID/correction
            // /logic profile — AE3 должен увидеть актуальные targets после resume.
            $this->automationConfigCompiler->compileAffectedScopes(
                AutomationConfigRegistry::SCOPE_GROW_CYCLE,
                (int) $cycle->id,
            );

            $zone = $cycle->zone;
            $this->syncZoneStatus($zone, 'RUNNING');

            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'CYCLE_RESUMED',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $cycle->id,
                'payload_json' => [
                    'cycle_id' => $cycle->id,
                    'user_id' => $userId,
                    'source' => 'web',
                    'correlation_id' => $this->correlation->resolve(),
                ],
            ]);

            broadcast(new GrowCycleUpdated($cycle, 'RESUMED'));

            Log::info('Grow cycle resumed', [
                'zone_id' => $zone->id,
                'cycle_id' => $cycle->id,
                'user_id' => $userId,
            ]);

            return $cycle->fresh();
        });
    }

    /**
     * @param array<string, mixed> $data
     */
    public function harvest(GrowCycle $cycle, array $data, int $userId): GrowCycle
    {
        if ($cycle->status === GrowCycleStatus::HARVESTED || $cycle->status === GrowCycleStatus::ABORTED) {
            throw new \DomainException('Cycle is already completed');
        }

        return DB::transaction(function () use ($cycle, $data, $userId) {
            $cycle->update([
                'status' => GrowCycleStatus::HARVESTED,
                'actual_harvest_at' => now(),
                'batch_label' => $data['batch_label'] ?? $cycle->batch_label,
                'notes' => $data['notes'] ?? $cycle->notes,
            ]);
            $cycle->refresh();

            $zone = $cycle->zone;
            $this->canceller->cancelGrowCycleStartRuntimeState(
                $cycle,
                $zone,
                'grow_cycle_harvested',
                sprintf(
                    'Grow cycle %d harvested before AE3 start-cycle task completed',
                    (int) $cycle->id
                )
            );
            $this->canceller->cancelAllZoneAutomationState($cycle, $zone, 'grow_cycle_harvested');
            $this->syncZoneStatus($zone, 'NEW');

            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'CYCLE_HARVESTED',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $cycle->id,
                'payload_json' => [
                    'cycle_id' => $cycle->id,
                    'user_id' => $userId,
                    'source' => 'web',
                    'batch_label' => $cycle->batch_label,
                ],
            ]);

            broadcast(new GrowCycleUpdated($cycle, 'HARVESTED'));

            Log::info('Grow cycle harvested', [
                'zone_id' => $zone->id,
                'cycle_id' => $cycle->id,
                'user_id' => $userId,
            ]);

            return $cycle->fresh();
        });
    }

    /**
     * @param array<string, mixed> $data
     */
    public function abort(GrowCycle $cycle, array $data, int $userId): GrowCycle
    {
        if ($cycle->status === GrowCycleStatus::HARVESTED || $cycle->status === GrowCycleStatus::ABORTED) {
            throw new \DomainException('Cycle is already completed');
        }

        return DB::transaction(function () use ($cycle, $data, $userId) {
            $cycle->update([
                'status' => GrowCycleStatus::ABORTED,
                'notes' => $data['notes'] ?? $cycle->notes,
            ]);
            $cycle->refresh();

            $zone = $cycle->zone;
            $this->canceller->cancelGrowCycleStartRuntimeState($cycle, $zone);
            $this->canceller->cancelAllZoneAutomationState($cycle, $zone, 'grow_cycle_aborted');
            $this->syncZoneStatus($zone, 'NEW');

            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'CYCLE_ABORTED',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $cycle->id,
                'payload_json' => [
                    'cycle_id' => $cycle->id,
                    'user_id' => $userId,
                    'source' => 'web',
                    'reason' => $data['notes'] ?? 'Emergency abort',
                ],
            ]);

            broadcast(new GrowCycleUpdated($cycle, 'ABORTED'));

            Log::info('Grow cycle aborted', [
                'zone_id' => $zone->id,
                'cycle_id' => $cycle->id,
                'user_id' => $userId,
            ]);

            return $cycle->fresh();
        });
    }

    public function getByGreenhouse(int $greenhouseId, int $perPage = 50): LengthAwarePaginator
    {
        return GrowCycle::where('greenhouse_id', $greenhouseId)
            ->with(['zone', 'plant', 'recipeRevision.phases', 'currentPhase', 'currentStep'])
            ->orderBy('started_at', 'desc')
            ->paginate($perPage);
    }

    private function syncZoneStatus(Zone $zone, string $status): void
    {
        if ($zone->status === $status) {
            return;
        }

        $zone->update(['status' => $status]);
        $zone->refresh();
        event(new ZoneUpdated($zone));
    }
}
