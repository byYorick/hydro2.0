<?php

namespace App\Console\Commands;

use App\Models\GrowCycle;
use App\Models\SchedulerLog;
use App\Services\EffectiveTargetsService;
use Carbon\CarbonImmutable;
use Illuminate\Console\Command;
use Illuminate\Contracts\Cache\Lock;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class AutomationDispatchSchedules extends Command
{
    protected $signature = 'automation:dispatch-schedules {--zone-id=* : Ограничить dispatch указанными zone_id}';

    protected $description = 'Laravel scheduler dispatcher: планирование и отправка abstract scheduler задач в automation-engine';

    private const ACTIVE_ZONE_STATUSES = ['online', 'warning', 'RUNNING', 'PAUSED'];

    private const ACTIVE_CYCLE_STATUSES = ['PLANNED', 'RUNNING', 'PAUSED'];

    private const SUPPORTED_TASK_TYPES = [
        'irrigation',
        'lighting',
        'ventilation',
        'solution_change',
        'mist',
        'diagnostics',
    ];

    private const CATCHUP_POLICIES = ['skip', 'replay_limited', 'replay_all'];

    private const TERMINAL_STATUSES = ['completed', 'done', 'failed', 'rejected', 'expired', 'timeout', 'error', 'not_found'];

    private const TASK_NAME_PREFIX = 'laravel_scheduler_task';

    private const CYCLE_LOG_TASK_NAME = 'laravel_scheduler_cycle';

    private const BOOTSTRAP_LOG_TASK_NAME = 'laravel_scheduler_bootstrap';

    /**
     * @var array<int, CarbonImmutable>
     */
    private array $zoneCursorCache = [];

    /**
     * @var array<int, bool>
     */
    private array $zoneCursorLoaded = [];

    public function __construct(
        private readonly EffectiveTargetsService $effectiveTargetsService,
    ) {
        parent::__construct();
    }

    public function handle(): int
    {
        if (! $this->isDispatcherEnabled()) {
            $this->line('AUTOMATION_LARAVEL_SCHEDULER_ENABLED=0, dispatch skipped.');

            return self::SUCCESS;
        }

        $zoneFilter = collect($this->option('zone-id'))
            ->map(static fn ($value): int => (int) $value)
            ->filter(static fn (int $value): bool => $value > 0)
            ->unique()
            ->values()
            ->all();

        $lock = $this->acquireDispatchLock();
        if (! $lock) {
            Log::info('Laravel scheduler dispatcher skipped due to active lock');
            $this->line('Dispatch lock already acquired, skip current cycle.');

            return self::SUCCESS;
        }

        try {
            $stats = $this->dispatchCycle($zoneFilter);
            $this->line(sprintf(
                'Dispatch cycle finished: zones=%d schedules=%d attempted=%d success=%d pending_retry=%d',
                (int) ($stats['zones_total'] ?? 0),
                (int) ($stats['schedules_total'] ?? 0),
                (int) ($stats['attempted_dispatches'] ?? 0),
                (int) ($stats['successful_dispatches'] ?? 0),
                (int) ($stats['zones_pending_time_retry'] ?? 0),
            ));

            return self::SUCCESS;
        } finally {
            try {
                $lock->release();
            } catch (\Throwable $e) {
                Log::warning('Laravel scheduler dispatcher failed to release lock', [
                    'error' => $e->getMessage(),
                ]);
            }
        }
    }

    /**
     * @param  array<int, int>  $zoneFilter
     * @return array<string, mixed>
     */
    private function dispatchCycle(array $zoneFilter): array
    {
        $cfg = $this->schedulerConfig();
        $traceId = $this->newTraceId();
        $bootstrap = $this->bootstrapLease($cfg, $traceId);

        if (! $bootstrap['ready']) {
            $stats = [
                'bootstrap_status' => $bootstrap['bootstrap_status'],
                'zones_total' => 0,
                'zones_with_targets' => 0,
                'schedules_total' => 0,
                'attempted_dispatches' => 0,
                'successful_dispatches' => 0,
                'triggerless_schedules' => 0,
                'zones_pending_time_retry' => 0,
            ];
            $this->writeSchedulerLog(self::CYCLE_LOG_TASK_NAME, 'skipped', $stats);

            return $stats;
        }

        $headers = $this->schedulerHeaders($cfg, $traceId, $bootstrap['lease_id']);
        $zoneIds = $this->loadActiveZoneIds($zoneFilter);

        if ($zoneIds === []) {
            $stats = [
                'bootstrap_status' => $bootstrap['bootstrap_status'],
                'zones_total' => 0,
                'zones_with_targets' => 0,
                'schedules_total' => 0,
                'attempted_dispatches' => 0,
                'successful_dispatches' => 0,
                'triggerless_schedules' => 0,
                'zones_pending_time_retry' => 0,
            ];
            $this->writeSchedulerLog(self::CYCLE_LOG_TASK_NAME, 'completed', $stats);

            return $stats;
        }

        $effectiveTargetsByZone = $this->loadEffectiveTargetsByZone($zoneIds);
        $schedules = [];
        $zonesWithTargets = 0;

        foreach ($zoneIds as $zoneId) {
            $zonePayload = $effectiveTargetsByZone[$zoneId] ?? null;
            if (! is_array($zonePayload)) {
                continue;
            }
            $targets = $zonePayload['targets'] ?? null;
            if (! is_array($targets)) {
                continue;
            }

            $zonesWithTargets++;
            foreach ($this->buildSchedulesForZone($zoneId, $targets) as $schedule) {
                $schedules[] = $schedule;
            }
        }

        $attemptedDispatches = 0;
        $successfulDispatches = 0;
        $triggerlessCount = 0;
        $replayBudget = $cfg['catchup_rate_limit_per_cycle'];

        /** @var array<string, bool> $executedKeys */
        $executedKeys = [];
        /** @var array<int, CarbonImmutable> $zoneNow */
        $zoneNow = [];
        /** @var array<int, CarbonImmutable> $zoneLast */
        $zoneLast = [];
        /** @var array<int, bool> $zonesWithPendingTimeDispatch */
        $zonesWithPendingTimeDispatch = [];
        /** @var array<int, bool> $zonesWithSuccessfulTimeDispatch */
        $zonesWithSuccessfulTimeDispatch = [];

        $realNow = $this->nowUtc();

        foreach ($schedules as $schedule) {
            $zoneId = (int) ($schedule['zone_id'] ?? 0);
            $taskType = strtolower((string) ($schedule['type'] ?? ''));
            if ($zoneId <= 0 || $taskType === '') {
                continue;
            }

            $scheduleKey = $this->buildScheduleKey($zoneId, $schedule);
            if (isset($executedKeys[$scheduleKey])) {
                continue;
            }

            if (! isset($zoneNow[$zoneId])) {
                $zoneNow[$zoneId] = $realNow;
                $zoneLast[$zoneId] = $this->resolveZoneLastCheck($zoneId, $realNow, $cfg['cursor_persist_enabled']);
            }

            $now = $zoneNow[$zoneId];
            $last = $zoneLast[$zoneId];

            $intervalSec = $this->safePositiveInt($schedule['interval_sec'] ?? null);
            $taskName = $this->scheduleTaskLogName($zoneId, $taskType);

            if ($intervalSec > 0) {
                if ($this->shouldRunIntervalTask($taskName, $intervalSec, $now)) {
                    $attemptedDispatches++;
                    $dispatchResult = $this->dispatchSchedule(
                        zoneId: $zoneId,
                        schedule: $schedule,
                        triggerTime: $now,
                        scheduleKey: $scheduleKey,
                        cfg: $cfg,
                        headers: $headers,
                    );
                    if ($dispatchResult['dispatched']) {
                        $successfulDispatches++;
                        $executedKeys[$scheduleKey] = true;
                    }
                }

                continue;
            }

            $scheduleTime = $schedule['time'] ?? null;
            if (is_string($scheduleTime) && $scheduleTime !== '') {
                $crossings = $this->scheduleCrossings($last, $now, $scheduleTime);
                $plannedTriggers = $this->applyCatchupPolicy($crossings, $now, $cfg['catchup_policy'], $cfg['catchup_max_windows']);
                $hadDispatchSuccess = false;

                foreach ($plannedTriggers as $triggerTime) {
                    $isReplay = $triggerTime->lt($now);
                    if ($isReplay) {
                        if ($replayBudget <= 0) {
                            break;
                        }
                        $replayBudget--;
                    }

                    $dispatchTrigger = $triggerTime;
                    $dispatchSchedule = $schedule;
                    if ($isReplay) {
                        $dispatchPayload = is_array($schedule['payload'] ?? null)
                            ? $schedule['payload']
                            : [];
                        $dispatchPayload['catchup_original_trigger_time'] = $this->toIso($triggerTime);
                        $dispatchPayload['catchup_policy'] = $cfg['catchup_policy'];
                        $dispatchSchedule['payload'] = $dispatchPayload;

                        if ($now->diffInSeconds($triggerTime) > $cfg['due_grace_sec']) {
                            $dispatchTrigger = $now;
                        }
                    }

                    $attemptedDispatches++;
                    $dispatchResult = $this->dispatchSchedule(
                        zoneId: $zoneId,
                        schedule: $dispatchSchedule,
                        triggerTime: $dispatchTrigger,
                        scheduleKey: $scheduleKey,
                        cfg: $cfg,
                        headers: $headers,
                    );
                    if ($dispatchResult['dispatched']) {
                        $successfulDispatches++;
                        $hadDispatchSuccess = true;
                        $zonesWithSuccessfulTimeDispatch[$zoneId] = true;
                        break;
                    }
                }

                if ($plannedTriggers !== [] && ! $hadDispatchSuccess) {
                    $zonesWithPendingTimeDispatch[$zoneId] = true;
                }
                if ($plannedTriggers !== []) {
                    $executedKeys[$scheduleKey] = true;
                }

                continue;
            }

            $startTime = $schedule['start_time'] ?? null;
            $endTime = $schedule['end_time'] ?? null;
            if (is_string($startTime) && is_string($endTime) && $startTime !== '' && $endTime !== '') {
                $desiredNow = $this->isTimeInWindow($now->format('H:i:s'), $startTime, $endTime);
                $desiredLast = $this->isTimeInWindow($last->format('H:i:s'), $startTime, $endTime);
                if ($desiredNow !== $desiredLast) {
                    $attemptedDispatches++;
                    $dispatchResult = $this->dispatchSchedule(
                        zoneId: $zoneId,
                        schedule: $schedule,
                        triggerTime: $now,
                        scheduleKey: $scheduleKey,
                        cfg: $cfg,
                        headers: $headers,
                    );
                    if ($dispatchResult['dispatched']) {
                        $successfulDispatches++;
                    }
                }
                $executedKeys[$scheduleKey] = true;

                continue;
            }

            $triggerlessCount++;
        }

        $zonesPendingTimeRetry = 0;
        foreach ($zoneNow as $zoneId => $now) {
            $cursorRetryPending = isset($zonesWithPendingTimeDispatch[$zoneId]) && ! isset($zonesWithSuccessfulTimeDispatch[$zoneId]);
            if ($cursorRetryPending) {
                $zonesPendingTimeRetry++;
            }

            $cursorAt = $cursorRetryPending
                ? ($zoneLast[$zoneId] ?? $now)
                : $now;
            $this->zoneCursorCache[$zoneId] = $cursorAt;
            $this->persistZoneCursor($zoneId, $cursorAt, $cfg['catchup_policy'], $cfg['cursor_persist_enabled']);
        }

        $stats = [
            'bootstrap_status' => $bootstrap['bootstrap_status'],
            'zones_total' => count($zoneIds),
            'zones_with_targets' => $zonesWithTargets,
            'schedules_total' => count($schedules),
            'attempted_dispatches' => $attemptedDispatches,
            'successful_dispatches' => $successfulDispatches,
            'triggerless_schedules' => $triggerlessCount,
            'zones_pending_time_retry' => $zonesPendingTimeRetry,
        ];

        $this->writeSchedulerLog(self::CYCLE_LOG_TASK_NAME, 'completed', $stats);

        return $stats;
    }

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
            'catchup_policy' => $catchupPolicy,
            'catchup_max_windows' => max(1, (int) config('services.automation_engine.scheduler_catchup_max_windows', 3)),
            'catchup_rate_limit_per_cycle' => max(1, (int) config('services.automation_engine.scheduler_catchup_rate_limit_per_cycle', 20)),
            'dispatch_interval_sec' => max(10, (int) config('services.automation_engine.scheduler_dispatch_interval_sec', 60)),
            'active_task_ttl_sec' => max(30, (int) config('services.automation_engine.scheduler_active_task_ttl_sec', $expiresAfterSec)),
            'cursor_persist_enabled' => (bool) config('services.automation_engine.scheduler_cursor_persist_enabled', true),
        ];
    }

    private function newTraceId(): string
    {
        return Str::lower((string) Str::uuid());
    }

    /**
     * @param  array<string, mixed>  $cfg
     * @return array{ready: bool, lease_id: string|null, bootstrap_status: string}
     */
    private function bootstrapLease(array $cfg, string $traceId): array
    {
        if ($cfg['token'] === '') {
            Log::error('Laravel scheduler dispatcher: missing scheduler api token');
            $this->writeSchedulerLog(self::BOOTSTRAP_LOG_TASK_NAME, 'error', [
                'error' => 'missing_scheduler_api_token',
            ]);

            return [
                'ready' => false,
                'lease_id' => null,
                'bootstrap_status' => 'error',
            ];
        }

        $headers = $this->schedulerHeaders($cfg, $traceId, null);
        $payload = [
            'scheduler_id' => $cfg['scheduler_id'],
            'scheduler_version' => $cfg['scheduler_version'],
            'protocol_version' => $cfg['protocol_version'],
            'started_at' => $this->toIso($this->nowUtc()),
            'capabilities' => [
                'task_types' => self::SUPPORTED_TASK_TYPES,
                'dispatch_origin' => 'laravel',
            ],
        ];

        try {
            $response = Http::acceptJson()
                ->timeout($cfg['timeout_sec'])
                ->withHeaders($headers)
                ->post($cfg['api_url'].'/scheduler/bootstrap', $payload);
        } catch (ConnectionException $e) {
            Log::warning('Laravel scheduler dispatcher bootstrap failed: automation-engine unavailable', [
                'error' => $e->getMessage(),
            ]);
            $this->writeSchedulerLog(self::BOOTSTRAP_LOG_TASK_NAME, 'failed', [
                'error' => 'connection_error',
                'message' => $e->getMessage(),
            ]);

            return [
                'ready' => false,
                'lease_id' => null,
                'bootstrap_status' => 'failed',
            ];
        }

        if (! $response->successful()) {
            $this->writeSchedulerLog(self::BOOTSTRAP_LOG_TASK_NAME, 'failed', [
                'error' => 'http_error',
                'status_code' => $response->status(),
                'response' => $response->body(),
            ]);

            return [
                'ready' => false,
                'lease_id' => null,
                'bootstrap_status' => 'failed',
            ];
        }

        $body = $response->json();
        $data = is_array($body) ? ($body['data'] ?? null) : null;
        $bootstrapStatus = is_array($data)
            ? strtolower(trim((string) ($data['bootstrap_status'] ?? 'unknown')))
            : 'unknown';
        $leaseId = is_array($data)
            ? trim((string) ($data['lease_id'] ?? ''))
            : '';

        $ready = $bootstrapStatus === 'ready' && $leaseId !== '';
        $this->writeSchedulerLog(
            self::BOOTSTRAP_LOG_TASK_NAME,
            $ready ? 'ready' : $bootstrapStatus,
            [
                'bootstrap_status' => $bootstrapStatus,
                'lease_id' => $leaseId !== '' ? $leaseId : null,
            ],
        );

        return [
            'ready' => $ready,
            'lease_id' => $ready ? $leaseId : null,
            'bootstrap_status' => $bootstrapStatus,
        ];
    }

    /**
     * @param  array<string, mixed>  $cfg
     * @return array<string, string>
     */
    private function schedulerHeaders(array $cfg, string $traceId, ?string $leaseId): array
    {
        $headers = [
            'Accept' => 'application/json',
            'X-Trace-Id' => $traceId,
            'X-Scheduler-Id' => $cfg['scheduler_id'],
        ];

        if ($cfg['token'] !== '') {
            $headers['Authorization'] = 'Bearer '.$cfg['token'];
        }
        if (is_string($leaseId) && $leaseId !== '') {
            $headers['X-Scheduler-Lease-Id'] = $leaseId;
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
            ->whereIn('status', self::ACTIVE_ZONE_STATUSES)
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
            ->whereIn('status', self::ACTIVE_CYCLE_STATUSES)
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

    /**
     * @param  array<string, mixed>  $targets
     * @return array<int, array<string, mixed>>
     */
    private function buildSchedulesForZone(int $zoneId, array $targets): array
    {
        $schedules = [];

        $irrigation = is_array($targets['irrigation'] ?? null) ? $targets['irrigation'] : [];
        $irrigationSchedule = $targets['irrigation_schedule'] ?? ($irrigation['schedule'] ?? null);
        if ($this->isTaskScheduleEnabled('irrigation', $targets, $irrigation)) {
            foreach ($this->buildGenericTaskSchedules($zoneId, 'irrigation', $irrigation, $irrigationSchedule, $targets) as $schedule) {
                $schedules[] = $schedule;
            }
        }

        $lighting = is_array($targets['lighting'] ?? null) ? $targets['lighting'] : [];
        $lightingIntervalSec = $this->safePositiveInt(
            $lighting['interval_sec'] ?? ($lighting['every_sec'] ?? ($lighting['interval'] ?? null))
        );
        if ($this->isTaskScheduleEnabled('lighting', $targets, $lighting)) {
            $photoperiodHours = $lighting['photoperiod_hours'] ?? null;
            $startTime = is_string($lighting['start_time'] ?? null)
                ? $this->parseTimeSpec((string) $lighting['start_time'])
                : null;
            if ($photoperiodHours !== null && $startTime !== null && is_numeric($photoperiodHours)) {
                $startDt = CarbonImmutable::createFromFormat('Y-m-d H:i:s', $this->nowUtc()->toDateString().' '.$startTime, 'UTC');
                $endDt = $startDt->addSeconds((int) round((float) $photoperiodHours * 3600));
                $scheduleItem = [
                    'zone_id' => $zoneId,
                    'type' => 'lighting',
                    'start_time' => $startTime,
                    'end_time' => $endDt->format('H:i:s'),
                    'targets' => $targets,
                    'config' => $lighting,
                ];
                if ($lightingIntervalSec > 0) {
                    $scheduleItem['interval_sec'] = $lightingIntervalSec;
                }
                $schedules[] = $scheduleItem;
            } else {
                $lightingSchedule = $targets['lighting_schedule'] ?? null;
                if (is_string($lightingSchedule) && str_contains($lightingSchedule, '-')) {
                    [$rawStart, $rawEnd] = array_map('trim', explode('-', $lightingSchedule, 2));
                    $start = $this->parseTimeSpec($rawStart);
                    $end = $this->parseTimeSpec($rawEnd);
                    if ($start !== null && $end !== null) {
                        $scheduleItem = [
                            'zone_id' => $zoneId,
                            'type' => 'lighting',
                            'start_time' => $start,
                            'end_time' => $end,
                            'targets' => $targets,
                            'config' => $lighting,
                        ];
                        if ($lightingIntervalSec > 0) {
                            $scheduleItem['interval_sec'] = $lightingIntervalSec;
                        }
                        $schedules[] = $scheduleItem;
                    }
                } else {
                    foreach ($this->buildGenericTaskSchedules($zoneId, 'lighting', $lighting, $lightingSchedule, $targets) as $schedule) {
                        $schedules[] = $schedule;
                    }
                }
            }
        }

        $genericConfigs = [
            ['ventilation', is_array($targets['ventilation'] ?? null) ? $targets['ventilation'] : [], $targets['ventilation_schedule'] ?? null],
            ['solution_change', is_array($targets['solution_change'] ?? null) ? $targets['solution_change'] : [], $targets['solution_change_schedule'] ?? null],
            ['mist', is_array($targets['mist'] ?? null) ? $targets['mist'] : [], $targets['mist_schedule'] ?? null],
            ['diagnostics', is_array($targets['diagnostics'] ?? null) ? $targets['diagnostics'] : [], $targets['diagnostics_schedule'] ?? null],
        ];

        foreach ($genericConfigs as [$taskType, $config, $scheduleSpec]) {
            if (! $this->isTaskScheduleEnabled((string) $taskType, $targets, (array) $config)) {
                continue;
            }
            $source = $scheduleSpec ?? $config;
            foreach ($this->buildGenericTaskSchedules($zoneId, (string) $taskType, (array) $config, $source, $targets) as $schedule) {
                $schedules[] = $schedule;
            }
        }

        return $schedules;
    }

    /**
     * @param  array<string, mixed>  $config
     * @param  array<string, mixed>  $targets
     * @return array<int, array<string, mixed>>
     */
    private function buildGenericTaskSchedules(
        int $zoneId,
        string $taskType,
        array $config,
        mixed $scheduleSpec,
        array $targets,
    ): array {
        $schedules = [];

        foreach ($this->extractTimeSpecs($scheduleSpec) as $timeSpec) {
            $schedules[] = [
                'zone_id' => $zoneId,
                'type' => $taskType,
                'time' => $timeSpec,
                'targets' => $targets,
                'config' => $config,
            ];
        }

        $intervalSec = $this->safePositiveInt(
            $config['interval_sec'] ?? ($config['every_sec'] ?? ($config['interval'] ?? null))
        );
        if ($intervalSec > 0) {
            $schedules[] = [
                'zone_id' => $zoneId,
                'type' => $taskType,
                'interval_sec' => $intervalSec,
                'targets' => $targets,
                'config' => $config,
            ];
        }

        return $schedules;
    }

    /**
     * @param  array<string, mixed>  $targets
     * @param  array<string, mixed>  $config
     */
    private function isTaskScheduleEnabled(string $taskType, array $targets, array $config): bool
    {
        $taskToSubsystem = [
            'irrigation' => 'irrigation',
            'lighting' => 'lighting',
            'ventilation' => 'climate',
            'diagnostics' => 'diagnostics',
            'solution_change' => 'solution_change',
        ];
        $subsystemKey = $taskToSubsystem[$taskType] ?? null;
        if (is_string($subsystemKey)) {
            $enabled = $this->subsystemEnabledFromTargets($targets, $subsystemKey);
            if ($enabled === false) {
                return false;
            }
        }

        $execution = is_array($config['execution'] ?? null) ? $config['execution'] : [];
        if (($execution['force_skip'] ?? false) === true) {
            return false;
        }
        if (($config['force_skip'] ?? false) === true) {
            return false;
        }

        return true;
    }

    /**
     * @param  array<string, mixed>  $targets
     */
    private function subsystemEnabledFromTargets(array $targets, string $subsystemKey): ?bool
    {
        $extensions = $targets['extensions'] ?? null;
        if (! is_array($extensions)) {
            return null;
        }
        $subsystems = $extensions['subsystems'] ?? null;
        if (! is_array($subsystems)) {
            return null;
        }
        $subsystem = $subsystems[$subsystemKey] ?? null;
        if (! is_array($subsystem)) {
            return null;
        }
        $enabled = $subsystem['enabled'] ?? null;

        return is_bool($enabled) ? $enabled : null;
    }

    /**
     * @return array<int, string>
     */
    private function extractTimeSpecs(mixed $value): array
    {
        if ($value === null) {
            return [];
        }

        $rawItems = [];
        if (is_string($value)) {
            $rawItems = array_filter(array_map('trim', explode(',', $value)));
        } elseif (is_array($value)) {
            if (array_is_list($value)) {
                $rawItems = $value;
            } elseif (is_array($value['times'] ?? null)) {
                $rawItems = $value['times'];
            } elseif (is_string($value['time'] ?? null)) {
                $rawItems = [$value['time']];
            }
        }

        $result = [];
        foreach ($rawItems as $item) {
            $parsed = $this->parseTimeSpec((string) $item);
            if ($parsed !== null) {
                $result[] = $parsed;
            }
        }

        return $result;
    }

    private function parseTimeSpec(string $spec): ?string
    {
        $candidate = trim($spec);
        if ($candidate === '') {
            return null;
        }

        if (! preg_match('/^([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$/', $candidate, $matches)) {
            return null;
        }

        $hour = (int) $matches[1];
        $minute = (int) $matches[2];
        $second = isset($matches[3]) ? (int) $matches[3] : 0;

        return sprintf('%02d:%02d:%02d', $hour, $minute, $second);
    }

    private function safePositiveInt(mixed $value): int
    {
        if (! is_numeric($value)) {
            return 0;
        }
        $parsed = (int) $value;

        return $parsed > 0 ? $parsed : 0;
    }

    /**
     * @return array<int, CarbonImmutable>
     */
    private function scheduleCrossings(CarbonImmutable $last, CarbonImmutable $now, string $targetTime): array
    {
        if ($now->lt($last)) {
            [$last, $now] = [$now, $last];
        }

        $startDate = $last->startOfDay();
        $endDate = $now->startOfDay();
        $crossings = [];

        for ($cursor = $startDate; $cursor->lte($endDate); $cursor = $cursor->addDay()) {
            $candidate = CarbonImmutable::createFromFormat(
                'Y-m-d H:i:s',
                $cursor->toDateString().' '.$targetTime,
                'UTC',
            );
            if ($candidate->gt($last) && $candidate->lte($now)) {
                $crossings[] = $candidate;
            }
        }

        return $crossings;
    }

    /**
     * @param  array<int, CarbonImmutable>  $crossings
     * @return array<int, CarbonImmutable>
     */
    private function applyCatchupPolicy(
        array $crossings,
        CarbonImmutable $now,
        string $catchupPolicy,
        int $maxWindows,
    ): array {
        if ($crossings === []) {
            return [];
        }
        if ($catchupPolicy === 'skip') {
            return [$now];
        }
        if ($catchupPolicy === 'replay_limited') {
            return array_slice($crossings, max(0, count($crossings) - $maxWindows));
        }

        return $crossings;
    }

    private function shouldRunIntervalTask(string $taskName, int $intervalSec, CarbonImmutable $now): bool
    {
        if ($intervalSec <= 0) {
            return false;
        }

        $lastTerminalLog = SchedulerLog::query()
            ->where('task_name', $taskName)
            ->whereIn('status', ['completed', 'failed'])
            ->orderByDesc('created_at')
            ->orderByDesc('id')
            ->first(['created_at']);

        if (! $lastTerminalLog?->created_at) {
            return true;
        }

        $lastCompletedAt = CarbonImmutable::instance($lastTerminalLog->created_at)->utc();

        return $lastCompletedAt->addSeconds($intervalSec)->lte($now);
    }

    private function resolveZoneLastCheck(int $zoneId, CarbonImmutable $now, bool $cursorPersistEnabled): CarbonImmutable
    {
        if (isset($this->zoneCursorCache[$zoneId])) {
            return $this->zoneCursorCache[$zoneId];
        }

        $default = $now->subSeconds(max(30, (int) config('services.automation_engine.scheduler_dispatch_interval_sec', 60)));
        if (! $cursorPersistEnabled) {
            $this->zoneCursorCache[$zoneId] = $default;

            return $default;
        }

        if (isset($this->zoneCursorLoaded[$zoneId])) {
            $this->zoneCursorCache[$zoneId] = $default;

            return $default;
        }

        $this->zoneCursorLoaded[$zoneId] = true;
        $taskName = sprintf('scheduler_cursor_zone_%d', $zoneId);
        $row = SchedulerLog::query()
            ->where('task_name', $taskName)
            ->orderByDesc('created_at')
            ->orderByDesc('id')
            ->first(['details']);

        if ($row && is_array($row->details)) {
            $raw = $row->details['last_check'] ?? ($row->details['cursor_at'] ?? null);
            $parsed = $this->parseIsoDateTime(is_string($raw) ? $raw : null);
            if ($parsed !== null) {
                $this->zoneCursorCache[$zoneId] = $parsed;

                return $parsed;
            }
        }

        $this->zoneCursorCache[$zoneId] = $default;

        return $default;
    }

    private function persistZoneCursor(int $zoneId, CarbonImmutable $cursorAt, string $catchupPolicy, bool $cursorPersistEnabled): void
    {
        if (! $cursorPersistEnabled) {
            return;
        }

        $taskName = sprintf('scheduler_cursor_zone_%d', $zoneId);
        $this->writeSchedulerLog($taskName, 'cursor', [
            'zone_id' => $zoneId,
            'last_check' => $this->toIso($cursorAt),
            'cursor_at' => $this->toIso($cursorAt),
            'catchup_policy' => $catchupPolicy,
        ]);
    }

    /**
     * @param  array<string, mixed>  $schedule
     */
    private function buildScheduleKey(int $zoneId, array $schedule): string
    {
        $taskType = strtolower((string) ($schedule['type'] ?? ''));
        $time = $this->formatScheduleKeyValue($schedule['time'] ?? null);
        $start = $this->formatScheduleKeyValue($schedule['start_time'] ?? null);
        $end = $this->formatScheduleKeyValue($schedule['end_time'] ?? null);
        $interval = $this->formatScheduleKeyValue($schedule['interval_sec'] ?? null);

        return sprintf(
            'zone:%d|type:%s|time=%s|start=%s|end=%s|interval=%s',
            $zoneId,
            $taskType,
            $time,
            $start,
            $end,
            $interval,
        );
    }

    private function formatScheduleKeyValue(mixed $value): string
    {
        if ($value === null) {
            return 'None';
        }

        return trim((string) $value) !== '' ? (string) $value : 'None';
    }

    private function isTimeInWindow(string $nowTime, string $startTime, string $endTime): bool
    {
        $now = $this->timeToSeconds($nowTime);
        $start = $this->timeToSeconds($startTime);
        $end = $this->timeToSeconds($endTime);
        if ($now === null || $start === null || $end === null) {
            return false;
        }
        if ($start === $end) {
            return true;
        }
        if ($start < $end) {
            return $now >= $start && $now <= $end;
        }

        return $now >= $start || $now <= $end;
    }

    private function timeToSeconds(string $timeSpec): ?int
    {
        $parsed = $this->parseTimeSpec($timeSpec);
        if ($parsed === null) {
            return null;
        }
        [$hour, $minute, $second] = array_map('intval', explode(':', $parsed));

        return ($hour * 3600) + ($minute * 60) + $second;
    }

    /**
     * @param  array<string, mixed>  $schedule
     * @param  array<string, mixed>  $cfg
     * @param  array<string, string>  $headers
     * @return array{dispatched: bool, retryable: bool, reason: string}
     */
    private function dispatchSchedule(
        int $zoneId,
        array $schedule,
        CarbonImmutable $triggerTime,
        string $scheduleKey,
        array $cfg,
        array $headers,
    ): array {
        $taskType = strtolower((string) ($schedule['type'] ?? ''));
        if (! in_array($taskType, self::SUPPORTED_TASK_TYPES, true)) {
            return [
                'dispatched' => false,
                'retryable' => false,
                'reason' => 'unsupported_task_type',
            ];
        }

        if ($this->isScheduleBusy($scheduleKey, $cfg, $headers)) {
            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'schedule_busy',
            ];
        }

        $taskName = $this->scheduleTaskLogName($zoneId, $taskType);
        $payload = is_array($schedule['payload'] ?? null) ? $schedule['payload'] : [];
        if (! array_key_exists('targets', $payload)) {
            $payload['targets'] = is_array($schedule['targets'] ?? null) ? $schedule['targets'] : [];
        }
        if (! array_key_exists('config', $payload)) {
            $payload['config'] = is_array($schedule['config'] ?? null) ? $schedule['config'] : [];
        }
        $payload['trigger_time'] = $this->toIso($triggerTime);
        $payload['schedule_key'] = $scheduleKey;

        if (
            $taskType === 'lighting'
            && is_string($schedule['start_time'] ?? null)
            && is_string($schedule['end_time'] ?? null)
        ) {
            $payload['desired_state'] = $this->isTimeInWindow(
                $triggerTime->format('H:i:s'),
                (string) $schedule['start_time'],
                (string) $schedule['end_time'],
            );
            $payload['start_time'] = (string) $schedule['start_time'];
            $payload['end_time'] = (string) $schedule['end_time'];
        }

        $scheduledForIso = $this->toIso($triggerTime);
        $correlationAnchor = $scheduledForIso;
        if (is_string($payload['catchup_original_trigger_time'] ?? null)) {
            $rawCatchupTrigger = (string) $payload['catchup_original_trigger_time'];
            $parsedCatchupTrigger = $this->parseIsoDateTime($rawCatchupTrigger);
            if ($parsedCatchupTrigger !== null) {
                $correlationAnchor = $this->toIso($parsedCatchupTrigger);
            }
        }

        $presetCorrelationId = trim((string) ($schedule['correlation_id'] ?? ''));
        $correlationId = $presetCorrelationId !== ''
            ? $presetCorrelationId
            : $this->buildSchedulerCorrelationId(
                zoneId: $zoneId,
                taskType: $taskType,
                scheduledFor: $correlationAnchor,
                scheduleKey: $scheduleKey,
            );

        [$dueAtIso, $expiresAtIso] = $this->computeTaskDeadlines($triggerTime, $cfg['due_grace_sec'], $cfg['expires_after_sec']);

        $requestPayload = [
            'zone_id' => $zoneId,
            'task_type' => $taskType,
            'payload' => $payload,
            'scheduled_for' => $scheduledForIso,
            'due_at' => $dueAtIso,
            'expires_at' => $expiresAtIso,
            'correlation_id' => $correlationId,
        ];

        try {
            $response = Http::acceptJson()
                ->timeout($cfg['timeout_sec'])
                ->withHeaders($headers)
                ->post($cfg['api_url'].'/scheduler/task', $requestPayload);
        } catch (ConnectionException $e) {
            $this->writeSchedulerLog($taskName, 'failed', [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'error' => 'connection_error',
                'message' => $e->getMessage(),
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
            ]);

            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'connection_error',
            ];
        }

        if (! $response->successful()) {
            $this->writeSchedulerLog($taskName, 'failed', [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'error' => 'http_error',
                'status_code' => $response->status(),
                'response' => $response->body(),
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
            ]);

            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'http_error',
            ];
        }

        $body = $response->json();
        $data = is_array($body) ? ($body['data'] ?? null) : null;
        $taskId = is_array($data) ? trim((string) ($data['task_id'] ?? '')) : '';
        $taskStatus = is_array($data)
            ? strtolower(trim((string) ($data['status'] ?? 'accepted')))
            : 'accepted';
        $isDuplicate = (bool) (is_array($data) ? ($data['is_duplicate'] ?? false) : false);

        if ($taskId === '') {
            $this->writeSchedulerLog($taskName, 'failed', [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'error' => 'task_id_missing',
                'response' => $body,
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
            ]);

            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'task_id_missing',
            ];
        }

        $normalizedStatus = $this->normalizeTerminalStatus($taskStatus);
        if ($this->isTerminalStatus($normalizedStatus)) {
            $logStatus = $normalizedStatus === 'completed' ? 'completed' : 'failed';
            $this->writeSchedulerLog($taskName, $logStatus, [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'task_id' => $taskId,
                'status' => $normalizedStatus,
                'terminal_on_submit' => true,
                'is_duplicate' => $isDuplicate,
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
            ]);

            return [
                'dispatched' => $normalizedStatus === 'completed',
                'retryable' => $normalizedStatus !== 'completed',
                'reason' => 'terminal_'.$normalizedStatus,
            ];
        }

        $this->writeSchedulerLog($taskName, 'accepted', [
            'zone_id' => $zoneId,
            'task_type' => $taskType,
            'task_id' => $taskId,
            'status' => $taskStatus,
            'is_duplicate' => $isDuplicate,
            'scheduled_for' => $scheduledForIso,
            'due_at' => $dueAtIso,
            'expires_at' => $expiresAtIso,
            'schedule_key' => $scheduleKey,
            'correlation_id' => $correlationId,
            'accepted_at' => $this->toIso($this->nowUtc()),
        ]);

        Cache::put(
            $this->activeTaskCacheKey($scheduleKey),
            [
                'task_id' => $taskId,
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'accepted_at' => $this->toIso($this->nowUtc()),
            ],
            now()->addSeconds($cfg['active_task_ttl_sec']),
        );

        return [
            'dispatched' => true,
            'retryable' => false,
            'reason' => 'accepted',
        ];
    }

    /**
     * @param  array<string, mixed>  $cfg
     * @param  array<string, string>  $headers
     */
    private function isScheduleBusy(string $scheduleKey, array $cfg, array $headers): bool
    {
        $cacheKey = $this->activeTaskCacheKey($scheduleKey);
        $cached = Cache::get($cacheKey);
        if (! is_array($cached) && ! is_string($cached)) {
            return false;
        }

        $taskId = '';
        if (is_string($cached)) {
            $taskId = trim($cached);
        } elseif (is_array($cached)) {
            $taskId = trim((string) ($cached['task_id'] ?? ''));
        }
        if ($taskId === '') {
            Cache::forget($cacheKey);

            return false;
        }

        $status = $this->fetchTaskStatus($taskId, $cfg, $headers);
        if ($status === null) {
            return true;
        }
        if ($this->isTerminalStatus($status)) {
            Cache::forget($cacheKey);

            return false;
        }

        return true;
    }

    /**
     * @param  array<string, mixed>  $cfg
     * @param  array<string, string>  $headers
     */
    private function fetchTaskStatus(string $taskId, array $cfg, array $headers): ?string
    {
        try {
            $response = Http::acceptJson()
                ->timeout($cfg['timeout_sec'])
                ->withHeaders($headers)
                ->get($cfg['api_url'].'/scheduler/task/'.urlencode($taskId));
        } catch (\Throwable) {
            return null;
        }

        if ($response->status() === 404) {
            return 'not_found';
        }
        if (! $response->successful()) {
            return null;
        }

        $body = $response->json();
        $data = is_array($body) ? ($body['data'] ?? null) : null;
        if (! is_array($data)) {
            return null;
        }

        $status = strtolower(trim((string) ($data['status'] ?? '')));
        if ($status === '') {
            return null;
        }

        return $this->normalizeTerminalStatus($status);
    }

    private function activeTaskCacheKey(string $scheduleKey): string
    {
        return 'laravel_scheduler_active:'.sha1($scheduleKey);
    }

    private function scheduleTaskLogName(int $zoneId, string $taskType): string
    {
        return sprintf('%s_%s_zone_%d', self::TASK_NAME_PREFIX, $taskType, $zoneId);
    }

    private function normalizeTerminalStatus(string $status): string
    {
        if ($status === 'done') {
            return 'completed';
        }
        if ($status === 'error') {
            return 'failed';
        }

        return $status;
    }

    private function isTerminalStatus(string $status): bool
    {
        return in_array($status, self::TERMINAL_STATUSES, true);
    }

    private function buildSchedulerCorrelationId(
        int $zoneId,
        string $taskType,
        ?string $scheduledFor,
        ?string $scheduleKey,
    ): string {
        $base = sprintf(
            '%d|%s|%s|%s',
            $zoneId,
            $taskType,
            $scheduledFor ?? '',
            $scheduleKey ?? '',
        );
        $digest = substr(hash('sha256', $base), 0, 20);

        return sprintf('sch:z%d:%s:%s', $zoneId, $taskType, $digest);
    }

    /**
     * @return array{0:string,1:string}
     */
    private function computeTaskDeadlines(CarbonImmutable $scheduledFor, int $dueGraceSec, int $expiresAfterSec): array
    {
        $dueAt = $scheduledFor->addSeconds($dueGraceSec);
        $expiresAt = $scheduledFor->addSeconds($expiresAfterSec);

        return [$this->toIso($dueAt), $this->toIso($expiresAt)];
    }

    private function toIso(CarbonImmutable $value): string
    {
        return $value->format('Y-m-d\TH:i:s');
    }

    private function parseIsoDateTime(?string $value): ?CarbonImmutable
    {
        if (! is_string($value) || trim($value) === '') {
            return null;
        }

        try {
            return CarbonImmutable::parse($value)->utc()->setMicroseconds(0);
        } catch (\Throwable) {
            return null;
        }
    }

    private function nowUtc(): CarbonImmutable
    {
        return CarbonImmutable::now('UTC')->setMicroseconds(0);
    }

    /**
     * @param  array<string, mixed>  $details
     */
    private function writeSchedulerLog(string $taskName, string $status, array $details): void
    {
        try {
            SchedulerLog::query()->create([
                'task_name' => $taskName,
                'status' => $status,
                'details' => $details,
            ]);
        } catch (\Throwable $e) {
            Log::warning('Failed to write scheduler log from laravel dispatcher', [
                'task_name' => $taskName,
                'status' => $status,
                'error' => $e->getMessage(),
            ]);
        }
    }
}
