<?php

namespace App\Console\Commands;

use App\Services\ZoneAutomationIntentService;
use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Watchdog для застрявших AE3 tasks и orphan scheduler intents.
 *
 * Обрабатывает:
 *  1. stage_deadline_at истёк — worker не уложился в deadline stage.
 *  2. Task claimed слишком давно без stage_deadline_at — fallback защита.
 *  3. running/waiting_command без deadline и без прогресса по updated_at.
 *  4. Orphan pending intents планировщика без active ae_task.
 *  5. Zombie workflow: активная фаза без running ae_task → rollback.
 *
 * Найденные tasks помечаются `failed`, связанные intents синхронизируются.
 */
class Ae3ReapStaleTasks extends Command
{
    protected $signature = 'ae3:reap-stale-tasks
        {--claim-stale-after=300 : Секунды с момента claim без прогресса}
        {--progress-stale-after=900 : Секунды без прогресса для running/waiting_command без deadline}
        {--orphan-intent-after=900 : Секунды pending intent без ae_task}';

    protected $description = 'Помечает зависшие AE3 tasks и orphan scheduler intents как failed';

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

        $activeStatuses = ['claimed', 'running', 'waiting_command'];

        $reapedKeys = [];

        // 1) Task пропустил stage_deadline_at
        $deadlineRows = DB::table('ae_tasks')
            ->whereIn('status', $activeStatuses)
            ->whereNotNull('stage_deadline_at')
            ->where('stage_deadline_at', '<', $now)
            ->get(['zone_id', 'idempotency_key']);

        $deadlineReaped = DB::table('ae_tasks')
            ->whereIn('status', $activeStatuses)
            ->whereNotNull('stage_deadline_at')
            ->where('stage_deadline_at', '<', $now)
            ->update([
                'status' => 'failed',
                'completed_at' => $now,
                'updated_at' => $now,
                'error_code' => 'stage_deadline_exceeded',
                'error_message' => 'Task stage deadline exceeded; reaped by watchdog',
            ]);

        foreach ($deadlineRows as $row) {
            $reapedKeys[] = [
                'zone_id' => (int) $row->zone_id,
                'idempotency_key' => (string) $row->idempotency_key,
                'error_code' => 'stage_deadline_exceeded',
                'error_message' => 'Task stage deadline exceeded; reaped by watchdog',
            ];
        }

        // 2) Claimed давно, deadline не установлен
        $claimStaleRows = DB::table('ae_tasks')
            ->where('status', 'claimed')
            ->whereNull('stage_deadline_at')
            ->whereNotNull('claimed_at')
            ->where('claimed_at', '<', $claimStaleThreshold)
            ->get(['zone_id', 'idempotency_key']);

        $claimStaleReaped = DB::table('ae_tasks')
            ->where('status', 'claimed')
            ->whereNull('stage_deadline_at')
            ->whereNotNull('claimed_at')
            ->where('claimed_at', '<', $claimStaleThreshold)
            ->update([
                'status' => 'failed',
                'completed_at' => $now,
                'updated_at' => $now,
                'error_code' => 'claim_stale',
                'error_message' => 'Task claimed without progress beyond threshold; reaped by watchdog',
            ]);

        foreach ($claimStaleRows as $row) {
            $reapedKeys[] = [
                'zone_id' => (int) $row->zone_id,
                'idempotency_key' => (string) $row->idempotency_key,
                'error_code' => 'claim_stale',
                'error_message' => 'Task claimed without progress beyond threshold; reaped by watchdog',
            ];
        }

        // 3) running/waiting_command без deadline и без обновления
        $progressStaleRows = DB::table('ae_tasks')
            ->whereIn('status', ['running', 'waiting_command'])
            ->whereNull('stage_deadline_at')
            ->where('updated_at', '<', $progressStaleThreshold)
            ->get(['zone_id', 'idempotency_key']);

        $progressStaleReaped = DB::table('ae_tasks')
            ->whereIn('status', ['running', 'waiting_command'])
            ->whereNull('stage_deadline_at')
            ->where('updated_at', '<', $progressStaleThreshold)
            ->update([
                'status' => 'failed',
                'completed_at' => $now,
                'updated_at' => $now,
                'error_code' => 'task_progress_stale',
                'error_message' => 'Task running/waiting_command without progress beyond threshold; reaped by watchdog',
            ]);

        foreach ($progressStaleRows as $row) {
            $reapedKeys[] = [
                'zone_id' => (int) $row->zone_id,
                'idempotency_key' => (string) $row->idempotency_key,
                'error_code' => 'task_progress_stale',
                'error_message' => 'Task running/waiting_command without progress beyond threshold; reaped by watchdog',
            ];
        }

        $intentSynced = 0;
        foreach ($reapedKeys as $item) {
            $before = DB::table('zone_automation_intents')
                ->where('zone_id', $item['zone_id'])
                ->where('idempotency_key', $item['idempotency_key'])
                ->whereIn('status', ['pending', 'claimed', 'running'])
                ->count();

            $this->intentService->syncIntentFailedFromAeTask(
                zoneId: $item['zone_id'],
                idempotencyKey: $item['idempotency_key'],
                errorCode: $item['error_code'],
                errorMessage: $item['error_message'],
            );

            if ($before > 0) {
                $intentSynced++;
            }
        }

        // 4) Orphan pending intents: нет active ae_task или связанная ae_task уже terminal failed
        $orphanIntents = DB::select(
            "
            SELECT zi.zone_id, zi.idempotency_key
            FROM zone_automation_intents zi
            WHERE zi.status = 'pending'
              AND zi.created_at < ?
              AND (
                  EXISTS (
                      SELECT 1
                      FROM ae_tasks t
                      WHERE t.zone_id = zi.zone_id
                        AND t.idempotency_key = zi.idempotency_key
                        AND t.status = 'failed'
                  )
                  OR NOT EXISTS (
                      SELECT 1
                      FROM ae_tasks t
                      WHERE t.zone_id = zi.zone_id
                        AND t.idempotency_key = zi.idempotency_key
                        AND t.status IN ('pending', 'claimed', 'running', 'waiting_command')
                  )
              )
            ",
            [$orphanIntentThreshold],
        );

        $orphanReaped = 0;
        foreach ($orphanIntents as $intent) {
            $this->intentService->markIntentFailed(
                zoneId: (int) $intent->zone_id,
                idempotencyKey: (string) $intent->idempotency_key,
                errorCode: 'scheduler_intent_orphan_pending',
                errorMessage: 'Scheduler intent pending without active ae_task beyond threshold; reaped by watchdog',
            );
            $orphanReaped++;
        }

        // 5) Zombie workflow: активная фаза без running ae_task → rollback
        $workflowReconciled = DB::update(
            "
            UPDATE zone_workflow_state zws
            SET workflow_phase = CASE
                    WHEN LOWER(zws.workflow_phase) IN ('irrigating', 'irrig_recirc') THEN 'ready'
                    ELSE 'idle'
                END,
                scheduler_task_id = NULL,
                updated_at = ?,
                payload = COALESCE(zws.payload, '{}'::jsonb) || jsonb_build_object(
                    'ae3_watchdog_rollback', true,
                    'ae3_watchdog_rollback_at', CAST(? AS text)
                )
            WHERE LOWER(zws.workflow_phase) IN ('tank_filling', 'tank_recirc', 'irrigating', 'irrig_recirc')
              AND NOT EXISTS (
                  SELECT 1
                  FROM ae_tasks t
                  WHERE t.zone_id = zws.zone_id
                    AND t.status IN ('pending', 'claimed', 'running', 'waiting_command')
              )
            ",
            [$now, $now->toIso8601String()],
        );

        $taskTotal = $deadlineReaped + $claimStaleReaped + $progressStaleReaped;
        if ($taskTotal > 0 || $orphanReaped > 0 || $workflowReconciled > 0) {
            Log::warning('AE3 watchdog reaped stale automation resources', [
                'stage_deadline_exceeded' => $deadlineReaped,
                'claim_stale' => $claimStaleReaped,
                'task_progress_stale' => $progressStaleReaped,
                'intent_synced' => $intentSynced,
                'orphan_intents' => $orphanReaped,
                'workflow_reconciled' => $workflowReconciled,
                'total_tasks' => $taskTotal,
            ]);
            $this->warn(sprintf(
                'Reaped tasks=%d (deadline=%d, claim=%d, progress=%d), intents_synced=%d, orphan_intents=%d, workflow_reconciled=%d',
                $taskTotal,
                $deadlineReaped,
                $claimStaleReaped,
                $progressStaleReaped,
                $intentSynced,
                $orphanReaped,
                $workflowReconciled,
            ));
        } else {
            if ($workflowReconciled > 0) {
                $this->warn(sprintf('Reconciled stale workflow states: %d', $workflowReconciled));
            } else {
                $this->info('No stale tasks or orphan intents found');
            }
        }

        return self::SUCCESS;
    }
}
