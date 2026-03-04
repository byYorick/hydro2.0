<?php

namespace App\Console\Commands;

use App\Services\AutomationScheduler\SchedulerConstants;
use App\Services\AutomationScheduler\SchedulerCycleService;
use Illuminate\Console\Command;
use Illuminate\Contracts\Cache\Lock;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Log;

class AutomationDispatchSchedules extends Command
{
    protected $signature = 'automation:dispatch-schedules {--zone-id=* : Ограничить dispatch указанными zone_id}';

    protected $description = 'Laravel scheduler dispatcher: планирование и отправка abstract scheduler задач в automation-engine';

    public function __construct(
        private readonly SchedulerCycleService $schedulerCycleService,
    ) {
        parent::__construct();
    }

    public function handle(): int
    {
        if (! $this->isDispatcherEnabled()) {
            $this->line('AUTOMATION_LARAVEL_SCHEDULER_ENABLED=0, dispatch skipped.');

            return self::SUCCESS;
        }

        $zoneFilter = $this->resolveZoneFilter();
        $lockResult = $this->acquireDispatchLock();
        if ($lockResult['state'] === 'busy') {
            Log::info('Laravel scheduler dispatcher skipped due to active lock');
            $this->line('Dispatch lock already acquired, skip current cycle.');

            return self::SUCCESS;
        }
        if ($lockResult['state'] === 'error') {
            Log::error('Laravel scheduler dispatcher lock acquisition failed', [
                'error' => $lockResult['error'],
            ]);

            return self::FAILURE;
        }

        $lock = $lockResult['lock'];
        try {
            $stats = $this->schedulerCycleService->runCycle($this->schedulerConfig(), $zoneFilter);
            $this->line(sprintf(
                'Dispatch cycle finished: zones=%d schedules=%d attempted=%d success=%d pending_retry=%d',
                (int) ($stats['zones_total'] ?? 0),
                (int) ($stats['schedules_total'] ?? 0),
                (int) ($stats['attempted_dispatches'] ?? 0),
                (int) ($stats['successful_dispatches'] ?? 0),
                (int) ($stats['zones_pending_time_retry'] ?? 0),
            ));

            return self::SUCCESS;
        } catch (\Throwable $e) {
            Log::error('Laravel scheduler dispatcher cycle failed', [
                'error' => $e->getMessage(),
            ]);

            return self::FAILURE;
        } finally {
            $this->releaseDispatchLock($lock);
        }
    }

    private function isDispatcherEnabled(): bool
    {
        return (bool) config('services.automation_engine.laravel_scheduler_enabled', false);
    }

    /**
     * @return array<int, int>
     */
    private function resolveZoneFilter(): array
    {
        return collect($this->option('zone-id'))
            ->map(static fn ($value): int => (int) $value)
            ->filter(static fn (int $value): bool => $value > 0)
            ->unique()
            ->values()
            ->all();
    }

    /**
     * @return array{state: 'acquired'|'busy'|'error', lock: Lock|null, error?: string}
     */
    private function acquireDispatchLock(): array
    {
        $ttlSec = max(10, (int) config('services.automation_engine.scheduler_lock_ttl_sec', 55));
        $lockKey = (string) config('services.automation_engine.scheduler_lock_key', 'automation:dispatch-schedules');

        try {
            $lock = Cache::lock($lockKey, $ttlSec);
            if (! $lock->get()) {
                return ['state' => 'busy', 'lock' => null];
            }

            return ['state' => 'acquired', 'lock' => $lock];
        } catch (\Throwable $e) {
            return ['state' => 'error', 'lock' => null, 'error' => $e->getMessage()];
        }
    }

    private function releaseDispatchLock(?Lock $lock): void
    {
        if (! $lock) {
            return;
        }

        try {
            $lock->release();
        } catch (\Throwable $e) {
            Log::warning('Laravel scheduler dispatcher failed to release lock', [
                'error' => $e->getMessage(),
            ]);
        }
    }

    /**
     * @return array<string, mixed>
     */
    private function schedulerConfig(): array
    {
        $dueGraceSec = max(1, (int) config('services.automation_engine.scheduler_due_grace_sec', 15));
        $expiresAfterSec = max($dueGraceSec + 1, (int) config('services.automation_engine.scheduler_expires_after_sec', 120));

        $catchupPolicy = strtolower((string) config('services.automation_engine.scheduler_catchup_policy', 'replay_limited'));
        if (! in_array($catchupPolicy, SchedulerConstants::CATCHUP_POLICIES, true)) {
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
}
