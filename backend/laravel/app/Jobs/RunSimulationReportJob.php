<?php

namespace App\Jobs;

use App\Models\DeviceNode;
use App\Models\GrowCycle;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\SimulationReport;
use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneSimulation;
use App\Services\GrowCycleService;
use App\Services\SimulationOrchestratorService;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Carbon;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class RunSimulationReportJob implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $timeout = 60;

    /**
     * Create a new job instance.
     */
    public function __construct(
        public int $simulationId
    ) {
        //
    }

    /**
     * Execute the job.
     */
    public function handle(GrowCycleService $growCycleService, SimulationOrchestratorService $orchestrator): void
    {
        $simulation = ZoneSimulation::find($this->simulationId);
        if (! $simulation) {
            Log::warning('RunSimulationReportJob: simulation not found', [
                'simulation_id' => $this->simulationId,
            ]);
            return;
        }

        $report = $simulation->relationLoaded('report')
            ? $simulation->report
            : $simulation->report()->first();
        if ($report && $report->status === 'completed') {
            return;
        }

        $scenario = $simulation->scenario ?? [];
        if (! is_array($scenario)) {
            Log::warning('RunSimulationReportJob: scenario missing', [
                'simulation_id' => $this->simulationId,
            ]);
            return;
        }
        $simMeta = $scenario['simulation'] ?? null;
        if (! is_array($simMeta)) {
            Log::warning('RunSimulationReportJob: simulation meta missing', [
                'simulation_id' => $this->simulationId,
            ]);
            return;
        }

        $simZoneId = $simMeta['sim_zone_id'] ?? null;
        $simGrowCycleId = $simMeta['sim_grow_cycle_id'] ?? null;
        if (! $simZoneId || ! $simGrowCycleId) {
            Log::warning('RunSimulationReportJob: simulation context ids missing', [
                'simulation_id' => $this->simulationId,
                'sim_zone_id' => $simZoneId,
                'sim_grow_cycle_id' => $simGrowCycleId,
            ]);
            return;
        }

        $simZone = Zone::find($simZoneId);
        $growCycle = GrowCycle::find($simGrowCycleId);
        if (! $simZone || ! $growCycle) {
            Log::warning('RunSimulationReportJob: simulation context not found', [
                'simulation_id' => $this->simulationId,
                'sim_zone_id' => $simZoneId,
                'sim_grow_cycle_id' => $simGrowCycleId,
            ]);
            return;
        }

        $context = [
            'zone' => $simZone,
            'grow_cycle' => $growCycle,
            'plant' => isset($simMeta['created_plant_id']) ? Plant::find($simMeta['created_plant_id']) : null,
            'recipe' => isset($simMeta['created_recipe_id']) ? Recipe::find($simMeta['created_recipe_id']) : null,
            'recipe_revision' => isset($simMeta['created_recipe_revision_id']) ? RecipeRevision::find($simMeta['created_recipe_revision_id']) : null,
            'node' => isset($simMeta['created_node_id']) ? DeviceNode::find($simMeta['created_node_id']) : null,
        ];

        $realDurationMinutes = $this->resolveRealDurationMinutes($simMeta);
        if (! $realDurationMinutes) {
            $orchestrator->executeFullSimulation($simulation, $context);
            return;
        }

        $growCycle = $growCycle->fresh(['currentPhase', 'recipeRevision.phases']);
        $currentPhase = $growCycle->currentPhase;
        if (! $currentPhase) {
            Log::warning('RunSimulationReportJob: current phase missing', [
                'simulation_id' => $this->simulationId,
                'grow_cycle_id' => $growCycle->id,
            ]);
            return;
        }

        $recipeRevision = $context['recipe_revision'] ?? $growCycle->recipeRevision;
        if (! $recipeRevision) {
            Log::warning('RunSimulationReportJob: recipe revision missing', [
                'simulation_id' => $this->simulationId,
                'grow_cycle_id' => $growCycle->id,
            ]);
            return;
        }

        $phases = $recipeRevision->phases()->orderBy('phase_index')->get();
        if ($phases->isEmpty()) {
            Log::warning('RunSimulationReportJob: recipe phases missing', [
                'simulation_id' => $this->simulationId,
                'recipe_revision_id' => $recipeRevision->id,
            ]);
            return;
        }

        $phaseSchedule = $this->buildPhaseScheduleSeconds($phases, $realDurationMinutes);
        $lastPhaseIndex = (int) $phases->max('phase_index');

        $summary = $this->buildReportSummary($simMeta, $simZone, $growCycle, $context);
        $report = SimulationReport::firstOrCreate(
            ['simulation_id' => $simulation->id],
            [
                'zone_id' => $simZone->id,
                'status' => 'running',
                'started_at' => now(),
                'summary_json' => $summary,
                'phases_json' => [],
                'metrics_json' => null,
                'errors_json' => null,
            ]
        );

        $phasesReport = is_array($report->phases_json) ? $report->phases_json : [];
        $updatedReport = false;

        if ($report->status !== 'running') {
            $report->status = 'running';
            $updatedReport = true;
        }
        if (! $report->started_at) {
            $report->started_at = now();
            $updatedReport = true;
        }
        if (empty($report->summary_json)) {
            $report->summary_json = $summary;
            $updatedReport = true;
        }
        if ($updatedReport) {
            $report->save();
        }

        if (empty($phasesReport)) {
            $phasesReport[] = $this->buildPhaseEntry($currentPhase, 'running');
            $report->update(['phases_json' => $phasesReport]);
            $this->recordSimulationEvent(
                $simulation->id,
                $simZone->id,
                'laravel',
                'report',
                'running',
                'Старт полного цикла симуляции',
                ['report_id' => $report->id]
            );
            $delaySeconds = $this->resolvePhaseDelaySeconds($currentPhase->phase_index, $phaseSchedule);
            $this->scheduleNextStep($delaySeconds);
            return;
        }

        $lastIndex = count($phasesReport) - 1;
        if ($lastIndex >= 0 && ($phasesReport[$lastIndex]['status'] ?? null) === 'running') {
            $phasesReport[$lastIndex]['completed_at'] = $phasesReport[$lastIndex]['completed_at'] ?? now()->toIso8601String();
            $phasesReport[$lastIndex]['status'] = 'completed';
        }

        if ($currentPhase->phase_index >= $lastPhaseIndex) {
            $this->finalizeSimulationReport($simulation, $simZone, $growCycle, $phasesReport);
            return;
        }

        try {
            $growCycle = $growCycleService->advancePhase($growCycle, $this->resolveSimulationUserId());
        } catch (\DomainException $e) {
            Log::warning('RunSimulationReportJob: advance phase halted', [
                'simulation_id' => $this->simulationId,
                'grow_cycle_id' => $growCycle->id,
                'error' => $e->getMessage(),
            ]);
            $this->finalizeSimulationReport($simulation, $simZone, $growCycle, $phasesReport);
            return;
        }

        $growCycle = $growCycle->fresh(['currentPhase']);
        $newPhase = $growCycle->currentPhase;
        if (! $newPhase) {
            $this->finalizeSimulationReport(
                $simulation,
                $simZone,
                $growCycle,
                $phasesReport,
                [
                    [
                        'message' => 'New phase missing after advance.',
                        'type' => 'RuntimeException',
                    ],
                ]
            );
            return;
        }

        $phasesReport[] = $this->buildPhaseEntry($newPhase, 'running');
        $report->update(['phases_json' => $phasesReport]);
        $this->recordSimulationEvent(
            $simulation->id,
            $simZone->id,
            'laravel',
            'phase',
            'advanced',
            'Переход к следующей фазе',
            [
                'phase_id' => $newPhase->id,
                'phase_index' => $newPhase->phase_index,
                'phase_name' => $newPhase->name,
            ]
        );

        $delaySeconds = $this->resolvePhaseDelaySeconds($newPhase->phase_index, $phaseSchedule);
        $this->scheduleNextStep($delaySeconds);
    }

    private function resolveRealDurationMinutes(array $simMeta): ?int
    {
        $realDuration = $simMeta['real_duration_minutes'] ?? null;
        if (! is_numeric($realDuration)) {
            return null;
        }

        $minutes = (int) $realDuration;
        return $minutes > 0 ? $minutes : null;
    }

    private function buildPhaseScheduleSeconds(Collection $phases, int $realDurationMinutes): array
    {
        $phaseCount = $phases->count();
        if ($phaseCount === 0) {
            return [];
        }

        $totalSeconds = max(1, (int) round($realDurationMinutes * 60));
        $weights = [];
        $totalWeight = 0.0;

        foreach ($phases as $phase) {
            $durationMinutes = 0.0;
            if (is_numeric($phase->duration_days)) {
                $durationMinutes += (float) $phase->duration_days * 24 * 60;
            }
            if (is_numeric($phase->duration_hours)) {
                $durationMinutes += (float) $phase->duration_hours * 60;
            }
            $weight = max(0.0, $durationMinutes);
            $weights[$phase->phase_index] = $weight;
            $totalWeight += $weight;
        }

        if ($totalWeight <= 0) {
            foreach ($phases as $phase) {
                $weights[$phase->phase_index] = 1.0;
            }
            $totalWeight = (float) $phaseCount;
        }

        $schedule = [];
        $allocated = 0;
        $lastIndex = $phaseCount - 1;
        $phases = $phases->values();

        foreach ($phases as $index => $phase) {
            $isLast = $index === $lastIndex;
            if ($isLast) {
                $seconds = max(1, $totalSeconds - $allocated);
            } else {
                $portion = $weights[$phase->phase_index] / $totalWeight;
                $seconds = max(1, (int) floor($totalSeconds * $portion));
                $allocated += $seconds;
            }
            $schedule[$phase->phase_index] = $seconds;
        }

        return $schedule;
    }

    private function resolvePhaseDelaySeconds(int $phaseIndex, array $schedule): int
    {
        $seconds = $schedule[$phaseIndex] ?? 60;
        return max(1, (int) $seconds);
    }

    private function scheduleNextStep(int $delaySeconds): void
    {
        self::dispatch($this->simulationId)->delay(now()->addSeconds($delaySeconds));
    }

    private function buildReportSummary(array $simMeta, Zone $zone, GrowCycle $cycle, array $context): array
    {
        return [
            'source_zone_id' => $simMeta['source_zone_id'] ?? null,
            'simulation_zone_id' => $zone->id,
            'simulation_grow_cycle_id' => $cycle->id,
            'created_plant_id' => $context['plant']?->id ?? ($simMeta['created_plant_id'] ?? null),
            'created_recipe_id' => $context['recipe']?->id ?? ($simMeta['created_recipe_id'] ?? null),
            'created_recipe_revision_id' => $context['recipe_revision']?->id ?? ($simMeta['created_recipe_revision_id'] ?? null),
            'created_node_id' => $context['node']?->id ?? ($simMeta['created_node_id'] ?? null),
            'created_node_uid' => $context['node']?->uid ?? ($simMeta['created_node_uid'] ?? null),
        ];
    }

    private function finalizeSimulationReport(
        ZoneSimulation $simulation,
        Zone $simZone,
        GrowCycle $growCycle,
        array $phasesReport,
        array $errors = []
    ): void {
        $report = $simulation->report()->first();
        if (! $report) {
            return;
        }

        if (! empty($phasesReport)) {
            $lastIndex = count($phasesReport) - 1;
            if (empty($phasesReport[$lastIndex]['completed_at'])) {
                $phasesReport[$lastIndex]['completed_at'] = now()->toIso8601String();
                $phasesReport[$lastIndex]['status'] = 'completed';
            }
        }

        if (empty($errors)) {
            try {
                $growCycle = app(GrowCycleService::class)->harvest($growCycle, ['batch_label' => 'SIM'], $this->resolveSimulationUserId());
                $this->recordSimulationEvent(
                    $simulation->id,
                    $simZone->id,
                    'laravel',
                    'cycle',
                    'harvested',
                    'Цикл симуляции завершен',
                    ['grow_cycle_id' => $growCycle->id]
                );
            } catch (\Throwable $e) {
                $errors[] = [
                    'message' => $e->getMessage(),
                    'type' => get_class($e),
                ];
                $this->recordSimulationEvent(
                    $simulation->id,
                    $simZone->id,
                    'laravel',
                    'cycle',
                    'failed',
                    'Ошибка завершения цикла симуляции',
                    ['error' => $e->getMessage()],
                    'error'
                );
            }
        }

        $finishedAt = now();
        $metrics = $this->buildReportMetrics($simulation->id, $simZone->id, $growCycle, $phasesReport, $finishedAt);

        $report->update([
            'status' => empty($errors) ? 'completed' : 'failed',
            'finished_at' => $finishedAt,
            'phases_json' => $phasesReport,
            'metrics_json' => $metrics,
            'errors_json' => empty($errors) ? null : $errors,
        ]);

        $this->recordSimulationEvent(
            $simulation->id,
            $simZone->id,
            'laravel',
            'report',
            empty($errors) ? 'completed' : 'failed',
            'Отчет симуляции сформирован',
            ['report_id' => $report->id]
        );
    }

    private function buildPhaseEntry($phase, string $status): array
    {
        return [
            'phase_id' => $phase->id,
            'phase_index' => $phase->phase_index,
            'name' => $phase->name,
            'started_at' => $phase->started_at?->toIso8601String(),
            'completed_at' => null,
            'status' => $status,
        ];
    }

    private function buildReportMetrics(int $simulationId, int $zoneId, GrowCycle $cycle, array $phases, Carbon $finishedAt): array
    {
        $startedAt = $cycle->started_at ?? $cycle->created_at ?? now();
        $durationSeconds = max(0, $finishedAt->diffInSeconds($startedAt, false));

        return [
            'phases_count' => count($phases),
            'nodes_count' => DeviceNode::query()->where('zone_id', $zoneId)->count(),
            'events_count' => DB::table('simulation_events')->where('simulation_id', $simulationId)->count(),
            'cycle_status' => $cycle->status,
            'duration_seconds' => $durationSeconds,
        ];
    }

    private function resolveSimulationUserId(): int
    {
        $userId = User::query()->orderBy('id')->value('id');
        if (! $userId) {
            throw new \RuntimeException('No users available to run simulation actions.');
        }

        return (int) $userId;
    }

    private function recordSimulationEvent(
        int $simulationId,
        int $zoneId,
        string $service,
        string $stage,
        string $status,
        string $message,
        array $payload = [],
        string $level = 'info',
    ): void {
        try {
            DB::table('simulation_events')->insert([
                'simulation_id' => $simulationId,
                'zone_id' => $zoneId,
                'service' => $service,
                'stage' => $stage,
                'status' => $status,
                'level' => $level,
                'message' => $message,
                'payload' => $payload ? json_encode($payload, JSON_UNESCAPED_UNICODE) : null,
                'occurred_at' => now(),
                'created_at' => now(),
            ]);
        } catch (\Throwable $e) {
            Log::warning('Failed to record simulation event', [
                'simulation_id' => $simulationId,
                'zone_id' => $zoneId,
                'service' => $service,
                'stage' => $stage,
                'status' => $status,
                'error' => $e->getMessage(),
            ]);
        }
    }
}
