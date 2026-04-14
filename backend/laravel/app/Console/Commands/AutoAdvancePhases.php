<?php

namespace App\Console\Commands;

use App\Models\GrowCycle;
use App\Services\AlertService;
use App\Services\GrowCycleService;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class AutoAdvancePhases extends Command
{
    protected $signature = 'phases:auto-advance {--dry-run : Не выполнять advance, только показать кандидатов}';

    protected $description = 'Auto-advance recipe phases для зон в control_mode=auto при истечении duration текущей фазы';

    private const ACTIVE_TASK_STATUSES = ['pending', 'claimed', 'running', 'waiting_command'];

    /**
     * `triggered_by` для системных переходов (cron) — null. FK на users nullable
     * по миграции 2025_12_25_151709_create_grow_cycle_transitions_table.php.
     */
    private const SYSTEM_USER_ID = null;

    public function __construct(
        private readonly GrowCycleService $growCycleService,
        private readonly AlertService $alertService,
    ) {
        parent::__construct();
    }

    public function handle(): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $now = now();

        $candidates = $this->fetchCandidates($now);

        if ($candidates->isEmpty()) {
            $this->info('No grow cycles to auto-advance');
            return self::SUCCESS;
        }

        $this->info(sprintf(
            'Found %d candidate cycle(s) for auto-advance%s',
            $candidates->count(),
            $dryRun ? ' (dry-run)' : '',
        ));

        $advanced = 0;
        $blocked = 0;
        $errors = 0;

        foreach ($candidates as $row) {
            $cycleId = (int) $row->id;
            $zoneId = (int) $row->zone_id;
            $strategy = (string) ($row->phase_advance_strategy ?? 'time');

            try {
                $blockReason = $this->checkGuards($zoneId);
                if ($blockReason !== null) {
                    $blocked++;
                    Log::info('Auto-advance blocked', [
                        'cycle_id' => $cycleId,
                        'zone_id' => $zoneId,
                        'reason' => $blockReason,
                    ]);
                    $this->observeOutcome($strategy, "blocked_{$blockReason}");
                    continue;
                }

                if ($dryRun) {
                    $this->line(" - cycle_id={$cycleId} zone_id={$zoneId} strategy={$strategy} would advance");
                    continue;
                }

                $cycle = GrowCycle::query()->findOrFail($cycleId);
                $hasNext = $this->hasNextPhase($cycle);

                if (! $hasNext) {
                    $this->emitRecipeCompletedAlert($cycle);
                    $this->observeOutcome($strategy, 'blocked_no_next_phase');
                    Log::info('Auto-advance: last phase reached, alert emitted', [
                        'cycle_id' => $cycleId,
                        'zone_id' => $zoneId,
                    ]);
                    continue;
                }

                $this->growCycleService->advancePhase($cycle, self::SYSTEM_USER_ID);
                $advanced++;
                $this->observeOutcome($strategy, 'advanced');
                Log::info('Phase auto-advanced', [
                    'cycle_id' => $cycleId,
                    'zone_id' => $zoneId,
                    'strategy' => $strategy,
                ]);
            } catch (\Throwable $e) {
                $errors++;
                $this->observeOutcome($strategy, 'error');
                Log::error('Auto-advance failed', [
                    'cycle_id' => $cycleId,
                    'zone_id' => $zoneId,
                    'error' => $e->getMessage(),
                    'exception' => $e,
                ]);
            }
        }

        $this->info(sprintf(
            'Auto-advance summary: advanced=%d blocked=%d errors=%d',
            $advanced, $blocked, $errors,
        ));

        return self::SUCCESS;
    }

    /**
     * Кандидаты: running grow_cycles в auto-зонах с истёкшим duration текущей фазы.
     */
    private function fetchCandidates(Carbon $now): \Illuminate\Support\Collection
    {
        return DB::table('grow_cycles as gc')
            ->join('zones as z', 'z.id', '=', 'gc.zone_id')
            ->join('grow_cycle_phases as gcp', 'gcp.id', '=', 'gc.current_phase_id')
            ->where('gc.status', 'RUNNING')
            ->where('z.control_mode', 'auto')
            ->whereNotNull('gcp.started_at')
            ->where('gcp.phase_advance_strategy', 'time')
            ->where(function ($q) use ($now) {
                // started_at + duration_hours + duration_days*24 < now
                $q->whereRaw(
                    "gcp.started_at + make_interval(hours => COALESCE(gcp.duration_hours,0)) + make_interval(days => COALESCE(gcp.duration_days,0)) < ?",
                    [$now->toDateTimeString()],
                );
            })
            ->select([
                'gc.id',
                'gc.zone_id',
                'gc.current_phase_id',
                'gcp.phase_advance_strategy',
                'gcp.duration_hours',
                'gcp.duration_days',
                'gcp.started_at',
            ])
            ->get();
    }

    /**
     * Возвращает причину блокировки или null если можно advance.
     * Reasons (label-friendly): active_task, critical_alert.
     */
    private function checkGuards(int $zoneId): ?string
    {
        $hasActiveTask = DB::table('ae_tasks')
            ->where('zone_id', $zoneId)
            ->whereIn('status', self::ACTIVE_TASK_STATUSES)
            ->exists();

        if ($hasActiveTask) {
            return 'active_task';
        }

        $hasCriticalAlert = DB::table('alerts')
            ->where('zone_id', $zoneId)
            ->where('status', 'ACTIVE')
            ->whereIn('severity', ['error', 'critical'])
            ->exists();

        if ($hasCriticalAlert) {
            return 'critical_alert';
        }

        return null;
    }

    private function hasNextPhase(GrowCycle $cycle): bool
    {
        $currentPhase = $cycle->currentPhase;
        if (! $currentPhase || ! $currentPhase->recipeRevisionPhase) {
            return false;
        }

        return $cycle->recipeRevision
            ?->phases()
            ->where('phase_index', '>', $currentPhase->recipeRevisionPhase->phase_index)
            ->exists() ?? false;
    }

    private function emitRecipeCompletedAlert(GrowCycle $cycle): void
    {
        $this->alertService->createOrUpdateActive([
            'code' => 'biz_recipe_completed_review_required',
            'type' => 'AE3 Recipe Completed Review Required',
            'severity' => 'warning',
            'category' => 'agronomy',
            'source' => 'biz',
            'zone_id' => $cycle->zone_id,
            'details' => [
                'cycle_id' => $cycle->id,
                'recipe_revision_id' => $cycle->recipe_revision_id,
                'current_phase_id' => $cycle->current_phase_id,
                'message' => 'Все фазы рецепта пройдены. Требуется решение агронома: продлить, закрыть цикл или переключить рецепт.',
                'component' => 'cron:phases:auto-advance',
                'dedupe_key' => sprintf(
                    'biz_recipe_completed_review_required|cycle:%d',
                    $cycle->id,
                ),
            ],
        ]);
    }

    private function observeOutcome(string $strategy, string $outcome): void
    {
        // Prometheus метрика будет добавлена через telemetry-aggregator или прямой counter.
        // Пока что — log для grep-friendly observability.
        Log::debug('Phase auto-advance outcome', [
            'strategy' => $strategy,
            'outcome' => $outcome,
        ]);
    }
}
