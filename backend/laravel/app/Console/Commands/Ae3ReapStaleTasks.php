<?php

namespace App\Console\Commands;

use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Watchdog для застрявших AE3 tasks.
 *
 * Обрабатывает два класса проблем:
 *  1. stage_deadline_at истёк — worker запустил stage, но не уложился в deadline
 *     (crash после claim, hang в ожидании command_response, etc).
 *  2. Task claimed слишком давно без прогресса — `claimed_at` старее порога,
 *     а `stage_deadline_at` не установлен (редкий fallback).
 *
 * Найденные tasks помечаются `failed` с соответствующим `error_code`, что
 * освобождает `partial unique (zone_id) WHERE status IN ('pending','claimed',
 * 'running','waiting_command')` и позволяет зоне получить новую задачу.
 * Lease зоны AE3 worker освобождает через TTL-rotation или finally-path.
 */
class Ae3ReapStaleTasks extends Command
{
    protected $signature = 'ae3:reap-stale-tasks {--claim-stale-after=300 : Секунды с момента claim без прогресса}';

    protected $description = 'Помечает зависшие AE3 tasks как failed (stage_deadline_at истёк или claim без прогресса)';

    public function handle(): int
    {
        $now = Carbon::now('UTC')->setMicroseconds(0);
        $claimStaleThreshold = $now->copy()->subSeconds((int) $this->option('claim-stale-after'));

        $activeStatuses = ['claimed', 'running', 'waiting_command'];

        // 1) Task пропустил stage_deadline_at
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

        // 2) Claimed давно, deadline не установлен — fallback защита
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

        $total = $deadlineReaped + $claimStaleReaped;
        if ($total > 0) {
            Log::warning('AE3 watchdog reaped stale tasks', [
                'stage_deadline_exceeded' => $deadlineReaped,
                'claim_stale' => $claimStaleReaped,
                'total' => $total,
            ]);
            $this->warn("Reaped {$total} stale tasks (deadline: {$deadlineReaped}, claim-stale: {$claimStaleReaped})");
        } else {
            $this->info('No stale tasks found');
        }

        return self::SUCCESS;
    }
}
