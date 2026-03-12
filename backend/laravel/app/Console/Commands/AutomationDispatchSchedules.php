<?php

namespace App\Console\Commands;

use App\Services\AutomationRuntimeConfigService;
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
        private readonly AutomationRuntimeConfigService $runtimeConfig,
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
                'lock_key' => $this->schedulerConfig()['lock_key'] ?? 'automation:dispatch-schedules',
            ]);

            return self::FAILURE;
        }

        $lock = $lockResult['lock'];
        $cycleStartedAt = microtime(true);
        try {
            $stats = $this->schedulerCycleService->runCycle($this->schedulerConfig(), $zoneFilter);
            $durationMs = (int) round((microtime(true) - $cycleStartedAt) * 1000);
            $this->line(sprintf(
                'Dispatch cycle finished: zones=%d schedules=%d attempted=%d success=%d pending_retry=%d duration_ms=%d',
                (int) ($stats['zones_total'] ?? 0),
                (int) ($stats['schedules_total'] ?? 0),
                (int) ($stats['attempted_dispatches'] ?? 0),
                (int) ($stats['successful_dispatches'] ?? 0),
                (int) ($stats['zones_pending_time_retry'] ?? 0),
                $durationMs,
            ));

            return self::SUCCESS;
        } catch (\Throwable $e) {
            $durationMs = (int) round((microtime(true) - $cycleStartedAt) * 1000);
            Log::error('Laravel scheduler dispatcher cycle failed', [
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
                'duration_ms' => $durationMs,
                'zone_filter' => $zoneFilter,
            ]);

            return self::FAILURE;
        } finally {
            $this->releaseDispatchLock($lock);
        }
    }

    private function isDispatcherEnabled(): bool
    {
        return $this->runtimeConfig->schedulerEnabled();
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
        $cfg = $this->schedulerConfig();
        $ttlSec = max(10, (int) ($cfg['lock_ttl_sec'] ?? 55));
        $lockKey = (string) ($cfg['lock_key'] ?? 'automation:dispatch-schedules');

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
            // Lock release failure risks deadlock on next cycle — treat as error.
            Log::error('Laravel scheduler dispatcher failed to release lock', [
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
                'lock_key' => $this->schedulerConfig()['lock_key'] ?? 'automation:dispatch-schedules',
            ]);
        }
    }

    /**
     * @return array<string, mixed>
     */
    private function schedulerConfig(): array
    {
        return $this->runtimeConfig->schedulerConfig();
    }
}
