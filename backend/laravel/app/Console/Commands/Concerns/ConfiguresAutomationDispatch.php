<?php

namespace App\Console\Commands\Concerns;

use App\Models\GrowCycle;
use App\Services\AutomationScheduler\SchedulerConstants;
use Carbon\CarbonImmutable;
use Illuminate\Contracts\Cache\Lock;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

/**
 * @deprecated Логика перенесена в App\Console\Commands\AutomationDispatchSchedules и App\Services\AutomationScheduler\SchedulerCycleService.
 */
trait ConfiguresAutomationDispatch
{
    private function isDispatcherEnabled(): bool
    {
        return (bool) config('services.automation_engine.laravel_scheduler_enabled', false);
    }

    private function acquireDispatchLock(): ?Lock
    {
        $ttlSec = max(10, (int) config('services.automation_engine.scheduler_lock_ttl_sec', 55));
        $lockKey = (string) config('services.automation_engine.scheduler_lock_key', 'automation:dispatch-schedules');

        try {
            $lock = Cache::lock($lockKey, $ttlSec);
            if (! $lock->get()) {
                return null;
            }

            return $lock;
        } catch (\Throwable $e) {
            Log::warning('Laravel scheduler dispatcher lock unavailable', [
                'error' => $e->getMessage(),
            ]);

            return null;
        }
    }

    /**
     * @return array<string, mixed>
     */
    private function schedulerConfig(): array
    {
        $dueGraceSec = max(1, (int) config('services.automation_engine.scheduler_due_grace_sec', 15));
        $expiresAfterSec = max($dueGraceSec + 1, (int) config('services.automation_engine.scheduler_expires_after_sec', 120));
        $hardStaleAfterSec = max(
            $expiresAfterSec + 1,
            (int) config('services.automation_engine.scheduler_hard_stale_after_sec', 1800)
        );

        $catchupPolicy = strtolower((string) config('services.automation_engine.scheduler_catchup_policy', 'replay_limited'));
        if (! in_array($catchupPolicy, self::CATCHUP_POLICIES, true)) {
            $catchupPolicy = 'replay_limited';
        }

        return [
            'api_url' => rtrim((string) config('services.automation_engine.api_url', 'http://automation-engine:9405'), '/'),
            'timeout_sec' => max(1.0, (float) config('services.automation_engine.timeout', 2.0)),
            'scheduler_id' => (string) config('services.automation_engine.scheduler_id', 'laravel-scheduler'),
            'scheduler_version' => (string) config('services.automation_engine.scheduler_version', '3.0.0'),
            'protocol_version' => (string) config('services.automation_engine.scheduler_protocol_version', '2.0'),
            'token' => trim((string) config('services.automation_engine.scheduler_api_token', '')),
            'due_grace_sec' => $dueGraceSec,
            'expires_after_sec' => $expiresAfterSec,
            'hard_stale_after_sec' => $hardStaleAfterSec,
            'catchup_policy' => $catchupPolicy,
            'catchup_max_windows' => max(1, (int) config('services.automation_engine.scheduler_catchup_max_windows', 3)),
            'catchup_rate_limit_per_cycle' => max(1, (int) config('services.automation_engine.scheduler_catchup_rate_limit_per_cycle', 20)),
            'dispatch_interval_sec' => max(10, (int) config('services.automation_engine.scheduler_dispatch_interval_sec', 60)),
            'active_task_ttl_sec' => max(30, (int) config('services.automation_engine.scheduler_active_task_ttl_sec', $expiresAfterSec)),
            'active_task_retention_days' => max(1, (int) config('services.automation_engine.scheduler_active_task_retention_days', 60)),
            'active_task_cleanup_batch' => max(1, (int) config('services.automation_engine.scheduler_active_task_cleanup_batch', 500)),
            'active_task_poll_batch' => max(1, (int) config('services.automation_engine.scheduler_active_task_poll_batch', 500)),
            'cursor_persist_enabled' => (bool) config('services.automation_engine.scheduler_cursor_persist_enabled', true),
        ];
    }

    /**
     * @param  array<string, mixed>  $cfg
     */
    private function cleanupTerminalActiveTasks(array $cfg): void
    {
        $retentionDays = max(1, (int) ($cfg['active_task_retention_days'] ?? 60));
        $batchLimit = max(1, (int) ($cfg['active_task_cleanup_batch'] ?? 500));
        $threshold = $this->nowUtc()->subDays($retentionDays);
        $deleted = $this->activeTaskStore->cleanupTerminalOlderThan($threshold, $batchLimit);

        if ($deleted > 0) {
            Log::info('Laravel scheduler active task cleanup executed', [
                'deleted' => $deleted,
                'retention_days' => $retentionDays,
                'batch_limit' => $batchLimit,
            ]);
        }
    }

    private function newTraceId(): string
    {
        return Str::lower((string) Str::uuid());
    }

    /**
     * @param  array<string, mixed>  $cfg
     * @return array<string, string>
     */
    private function schedulerHeaders(array $cfg, string $traceId): array
    {
        $headers = [
            'Accept' => 'application/json',
            'X-Trace-Id' => $traceId,
            'X-Scheduler-Id' => $cfg['scheduler_id'],
        ];

        if ($cfg['token'] !== '') {
            $headers['Authorization'] = 'Bearer '.$cfg['token'];
        }

        return $headers;
    }

    /**
     * @param  array<int, int>  $zoneFilter
     * @return array<int, int>
     */
    private function loadActiveZoneIds(array $zoneFilter): array
    {
        $query = DB::table('zones')
            ->select('id')
            ->whereIn(DB::raw('lower(status)'), SchedulerConstants::ACTIVE_ZONE_STATUSES_LOWER)
            ->orderBy('id');

        if ($zoneFilter !== []) {
            $query->whereIn('id', $zoneFilter);
        }

        return $query->pluck('id')
            ->map(static fn ($value): int => (int) $value)
            ->filter(static fn (int $value): bool => $value > 0)
            ->values()
            ->all();
    }

    /**
     * @param  array<int, int>  $zoneIds
     * @return array<int, array<string, mixed>>
     */
    private function loadEffectiveTargetsByZone(array $zoneIds): array
    {
        if ($zoneIds === []) {
            return [];
        }

        $cycles = GrowCycle::query()
            ->select(['id', 'zone_id'])
            ->whereIn('zone_id', $zoneIds)
            ->whereIn(DB::raw('upper(status)'), self::ACTIVE_CYCLE_STATUSES)
            ->orderByDesc('id')
            ->get();

        if ($cycles->isEmpty()) {
            return [];
        }

        $effectiveByCycleId = $this->effectiveTargetsService->getEffectiveTargetsBatch(
            $cycles->pluck('id')->map(static fn ($value): int => (int) $value)->all()
        );

        $result = [];
        foreach ($cycles as $cycle) {
            $zoneId = (int) $cycle->zone_id;
            if ($zoneId <= 0 || isset($result[$zoneId])) {
                continue;
            }

            $payload = $effectiveByCycleId[(int) $cycle->id] ?? null;
            if (! is_array($payload)) {
                continue;
            }
            if (isset($payload['error'])) {
                continue;
            }
            if (! is_array($payload['targets'] ?? null)) {
                continue;
            }

            $result[$zoneId] = $payload;
        }

        return $result;
    }
}
