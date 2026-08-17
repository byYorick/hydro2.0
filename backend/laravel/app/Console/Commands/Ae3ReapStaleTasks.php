<?php

namespace App\Console\Commands;

use App\Services\ZoneAutomationIntentService;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Watchdog для orphan scheduler intents и наблюдаемости stale AE3 tasks.
 *
 * Terminal fail `ae_tasks` пишет только ae3lite (fail-safe OFF → fail → lease release).
 * Laravel не имеет права `UPDATE ae_tasks SET status='failed'` и не трогает
 * `zone_workflow_state` без CAS — иначе dual-write оставляет насос ON.
 *
 * Обрабатывает:
 *  1. Stale ae_tasks (deadline / claim / progress) — только alert + лог.
 *  2. Orphan pending intents без ae_task. Не терминалит retryable
 *     laravel_scheduler intents и lighting/irrigation/solution_* backpressure.
 */
class Ae3ReapStaleTasks extends Command
{
    /**
     * @var list<string>
     */
    private const BACKPRESSURE_TASK_TYPES = [
        'irrigation',
        'lighting',
        'solution_topup',
        'solution_change',
        'irrigation_start',
    ];

    /**
     * @var list<string>
     */
    private const BACKPRESSURE_INTENT_TYPES = [
        'IRRIGATE_ONCE',
        'LIGHTING_TICK',
        'SOLUTION_TOPUP',
        'SOLUTION_CHANGE',
    ];

    protected $signature = 'ae3:reap-stale-tasks
        {--claim-stale-after=300 : Секунды с момента claim без прогресса (только лог)}
        {--progress-stale-after=900 : Секунды без прогресса для running/waiting_command без deadline (только лог)}
        {--orphan-intent-after=900 : Секунды pending intent без ae_task}
        {--deadline-grace-sec=30 : Grace после stage_deadline_at, чтобы AE успел самозавершить poll-deadline}';

    protected $description = 'Логирует stale AE3 tasks и reap orphan scheduler intents без записи ae_tasks/workflow';

    public function __construct(
        private readonly ZoneAutomationIntentService $intentService,
    ) {
        parent::__construct();
    }

    public function handle(): int
    {
        $now = Carbon::now('UTC')->setMicroseconds(0);
        $claimStaleThreshold = $now->copy()->subSeconds((int) $this->option('claim-stale-after'));
        $progressStaleThreshold = $now->copy()->subSeconds((int) $this->option('progress-stale-after'));
        $orphanIntentThreshold = $now->copy()->subSeconds((int) $this->option('orphan-intent-after'));
        $deadlineGraceSec = max(0, (int) $this->option('deadline-grace-sec'));
        $deadlineReapThreshold = $now->copy()->subSeconds($deadlineGraceSec);

        $staleTasks = $this->collectStaleTasks(
            deadlineThreshold: $deadlineReapThreshold,
            claimStaleThreshold: $claimStaleThreshold,
            progressStaleThreshold: $progressStaleThreshold,
        );
        $this->logStaleTasksWithoutMutating($staleTasks);

        $orphanStats = $this->reapOrphanPendingIntents($orphanIntentThreshold);

        $deadlineLogged = $this->countStaleByReason($staleTasks, 'stage_deadline_exceeded')
            + $this->countStaleByReason($staleTasks, 'ae3_command_poll_deadline_exceeded');
        $claimLogged = $this->countStaleByReason($staleTasks, 'claim_stale');
        $progressLogged = $this->countStaleByReason($staleTasks, 'task_progress_stale');

        if ($staleTasks !== [] || $orphanStats['reaped'] > 0 || $orphanStats['skipped'] > 0) {
            Log::warning('AE3 watchdog observed stale automation resources without mutating ae_tasks', [
                'stage_deadline_exceeded' => $deadlineLogged,
                'claim_stale' => $claimLogged,
                'task_progress_stale' => $progressLogged,
                'orphan_intents' => $orphanStats['reaped'],
                'orphan_intents_skipped' => $orphanStats['skipped'],
                'total_stale_tasks' => count($staleTasks),
            ]);
            $this->warn(sprintf(
                'Stale tasks logged=%d (deadline=%d, claim=%d, progress=%d), orphan_intents=%d, skipped=%d',
                count($staleTasks),
                $deadlineLogged,
                $claimLogged,
                $progressLogged,
                $orphanStats['reaped'],
                $orphanStats['skipped'],
            ));
        } else {
            $this->info('No stale tasks or orphan intents found');
        }

        return self::SUCCESS;
    }

    /**
     * @return list<array{zone_id: int, idempotency_key: string, status: string, reason: string}>
     */
    private function collectStaleTasks(
        Carbon $deadlineThreshold,
        Carbon $claimStaleThreshold,
        Carbon $progressStaleThreshold,
    ): array {
        $stale = [];

        foreach (['waiting_command', 'claimed', 'running'] as $status) {
            $reason = $status === 'waiting_command'
                ? 'ae3_command_poll_deadline_exceeded'
                : 'stage_deadline_exceeded';
            $rows = DB::table('ae_tasks')
                ->where('status', $status)
                ->whereNotNull('stage_deadline_at')
                ->where('stage_deadline_at', '<', $deadlineThreshold)
                ->get(['zone_id', 'idempotency_key', 'status']);
            foreach ($rows as $row) {
                $stale[] = $this->staleTaskRow($row, $reason);
            }
        }

        $claimStaleRows = DB::table('ae_tasks')
            ->where('status', 'claimed')
            ->whereNull('stage_deadline_at')
            ->whereNotNull('claimed_at')
            ->where('claimed_at', '<', $claimStaleThreshold)
            ->get(['zone_id', 'idempotency_key', 'status']);
        foreach ($claimStaleRows as $row) {
            $stale[] = $this->staleTaskRow($row, 'claim_stale');
        }

        $progressStaleRows = DB::table('ae_tasks')
            ->whereIn('status', ['running', 'waiting_command'])
            ->whereNull('stage_deadline_at')
            ->where('updated_at', '<', $progressStaleThreshold)
            ->get(['zone_id', 'idempotency_key', 'status']);
        foreach ($progressStaleRows as $row) {
            $stale[] = $this->staleTaskRow($row, 'task_progress_stale');
        }

        return $stale;
    }

    /**
     * @param  list<array{zone_id: int, idempotency_key: string, status: string, reason: string}>  $staleTasks
     */
    private function logStaleTasksWithoutMutating(array $staleTasks): void
    {
        foreach ($staleTasks as $item) {
            Log::warning('AE3 stale task left for ae3lite janitor; Laravel will not fail ae_tasks', [
                'zone_id' => $item['zone_id'],
                'idempotency_key' => $item['idempotency_key'],
                'status' => $item['status'],
                'reason' => $item['reason'],
            ]);
        }
    }

    /**
     * @return array{reaped: int, skipped: int}
     */
    private function reapOrphanPendingIntents(Carbon $orphanIntentThreshold): array
    {
        $orphanIntents = DB::select(
            "
            SELECT zi.zone_id, zi.idempotency_key, zi.intent_source, zi.task_type,
                   zi.intent_type, zi.retry_count, zi.max_retries
            FROM zone_automation_intents zi
            WHERE zi.status = 'pending'
              AND zi.created_at < ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM ae_tasks t
                  WHERE t.zone_id = zi.zone_id
                    AND t.idempotency_key = zi.idempotency_key
              )
            ",
            [$orphanIntentThreshold],
        );

        $reaped = 0;
        $skipped = 0;
        foreach ($orphanIntents as $intent) {
            if ($this->shouldSkipOrphanIntent($intent)) {
                Log::warning('AE3 watchdog skipped orphan scheduler intent (retryable or lighting/irrigation backpressure)', [
                    'zone_id' => (int) $intent->zone_id,
                    'idempotency_key' => (string) $intent->idempotency_key,
                    'intent_source' => (string) ($intent->intent_source ?? ''),
                    'task_type' => (string) ($intent->task_type ?? ''),
                    'intent_type' => (string) ($intent->intent_type ?? ''),
                    'retry_count' => (int) ($intent->retry_count ?? 0),
                    'max_retries' => (int) ($intent->max_retries ?? 3),
                ]);
                $skipped++;

                continue;
            }

            $this->intentService->markIntentFailed(
                zoneId: (int) $intent->zone_id,
                idempotencyKey: (string) $intent->idempotency_key,
                errorCode: 'scheduler_intent_orphan_pending',
                errorMessage: 'Scheduler intent pending without ae_task beyond threshold; reaped by watchdog',
            );
            $reaped++;
        }

        return ['reaped' => $reaped, 'skipped' => $skipped];
    }

    private function shouldSkipOrphanIntent(object $intent): bool
    {
        $source = strtolower(trim((string) ($intent->intent_source ?? '')));
        if ($source !== 'laravel_scheduler') {
            return false;
        }

        $taskType = strtolower(trim((string) ($intent->task_type ?? '')));
        if (in_array($taskType, self::BACKPRESSURE_TASK_TYPES, true)) {
            return true;
        }

        $intentType = strtoupper(trim((string) ($intent->intent_type ?? '')));
        if (in_array($intentType, self::BACKPRESSURE_INTENT_TYPES, true)) {
            return true;
        }

        $retryCount = (int) ($intent->retry_count ?? 0);
        $maxRetries = max(1, (int) ($intent->max_retries ?? 3));

        return $retryCount < $maxRetries;
    }

    /**
     * @param  list<array{zone_id: int, idempotency_key: string, status: string, reason: string}>  $staleTasks
     */
    private function countStaleByReason(array $staleTasks, string $reason): int
    {
        $count = 0;
        foreach ($staleTasks as $item) {
            if ($item['reason'] === $reason) {
                $count++;
            }
        }

        return $count;
    }

    /**
     * @return array{zone_id: int, idempotency_key: string, status: string, reason: string}
     */
    private function staleTaskRow(object $row, string $reason): array
    {
        return [
            'zone_id' => (int) $row->zone_id,
            'idempotency_key' => (string) $row->idempotency_key,
            'status' => (string) $row->status,
            'reason' => $reason,
        ];
    }
}
