<?php

namespace App\Services\AutomationScheduler;

use App\Models\Zone;
use App\Services\AutomationRuntimeConfigService;
use Carbon\CarbonImmutable;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\Response;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class ScheduleWorkspaceService
{
    public function __construct(
        private readonly ScheduleLoader $scheduleLoader,
        private readonly ZoneScheduleItemBuilder $zoneScheduleItemBuilder,
        private readonly ExecutionRunReadModel $executionRunReadModel,
        private readonly AutomationRuntimeConfigService $runtimeConfig,
    ) {}

    /**
     * @return array<string, mixed>
     */
    public function buildWorkspace(Zone $zone, string $horizon): array
    {
        $resolvedHorizon = $this->normalizeHorizon($horizon);
        $now = SchedulerRuntimeHelper::nowUtc();
        $horizonEnd = $this->resolveHorizonEnd($now, $resolvedHorizon);

        $effectiveTargetsByZone = $this->scheduleLoader->loadEffectiveTargetsByZone([$zone->id]);
        $zonePayload = is_array($effectiveTargetsByZone[$zone->id] ?? null) ? $effectiveTargetsByZone[$zone->id] : [];
        $targets = is_array($zonePayload['targets'] ?? null) ? $zonePayload['targets'] : [];

        $schedules = $targets !== []
            ? $this->zoneScheduleItemBuilder->buildSchedulesForZone($zone->id, $targets, $now)
            : [];

        $lastRunByTaskName = $this->scheduleLoader->loadLastRunBatch(
            $this->scheduleLoader->collectIntervalTaskNames($schedules)
        );
        $planWindows = $this->buildPlanWindows($zone->id, $schedules, $lastRunByTaskName, $now, $horizonEnd);
        $recentRuns = $this->executionRunReadModel->listForZone($zone->id, 10);
        $activeRun = collect($recentRuns)->first(static fn (array $run): bool => (bool) ($run['is_active'] ?? false));
        $capabilities = $this->capabilitiesForZone($zone, $planWindows);
        $laneMap = $this->buildLaneMap($planWindows, $capabilities);

        return [
            'control' => $this->buildControlSnapshot($zone, $now),
            'capabilities' => $capabilities,
            'plan' => [
                'horizon' => $resolvedHorizon,
                'lanes' => array_values($laneMap),
                'windows' => $planWindows,
                'summary' => [
                    'planned_total' => count($planWindows),
                    'suppressed_total' => 0,
                    'missed_total' => 0,
                ],
            ],
            'execution' => [
                'active_run' => $activeRun ?: null,
                'recent_runs' => $recentRuns,
                'counters' => $this->executionRunReadModel->countersForZone($zone->id),
                'latest_failure' => $this->executionRunReadModel->latestFailureForZone($zone->id),
            ],
        ];
    }

    private function normalizeHorizon(string $horizon): string
    {
        $normalized = strtolower(trim($horizon));

        return in_array($normalized, ['24h', '7d'], true) ? $normalized : '24h';
    }

    private function resolveHorizonEnd(CarbonImmutable $now, string $horizon): CarbonImmutable
    {
        return $horizon === '7d'
            ? $now->addDays(7)
            : $now->addDay();
    }

    /**
     * @param  array<int, ScheduleItem>  $schedules
     * @param  array<string, CarbonImmutable>  $lastRunByTaskName
     * @return array<int, array<string, mixed>>
     */
    private function buildPlanWindows(
        int $zoneId,
        array $schedules,
        array $lastRunByTaskName,
        CarbonImmutable $now,
        CarbonImmutable $horizonEnd,
    ): array {
        $windows = [];

        foreach ($schedules as $schedule) {
            if (! $schedule instanceof ScheduleItem) {
                continue;
            }

            foreach ($this->futureTriggersForSchedule($schedule, $lastRunByTaskName, $now, $horizonEnd) as $triggerAt) {
                $windows[] = [
                    'plan_window_id' => sprintf('%d:%s:%s', $zoneId, $schedule->scheduleKey, SchedulerRuntimeHelper::toIso($triggerAt)),
                    'zone_id' => $zoneId,
                    'task_type' => $this->publicTaskType($schedule->taskType),
                    'schedule_task_type' => $schedule->taskType,
                    'label' => $this->taskTypeLabel($schedule->taskType),
                    'schedule_key' => $schedule->scheduleKey,
                    'trigger_at' => SchedulerRuntimeHelper::toIso($triggerAt),
                    'origin' => 'effective_targets',
                    'state' => 'planned',
                    'mode' => $this->scheduleMode($schedule),
                ];
            }
        }

        usort($windows, static function (array $left, array $right): int {
            return strcmp((string) ($left['trigger_at'] ?? ''), (string) ($right['trigger_at'] ?? ''));
        });

        return $windows;
    }

    /**
     * @param  array<string, CarbonImmutable>  $lastRunByTaskName
     * @return array<int, CarbonImmutable>
     */
    private function futureTriggersForSchedule(
        ScheduleItem $schedule,
        array $lastRunByTaskName,
        CarbonImmutable $now,
        CarbonImmutable $horizonEnd,
    ): array {
        if ($schedule->time !== null) {
            return $this->futureDailyTriggers($schedule->time, $now, $horizonEnd);
        }

        if ($schedule->intervalSec > 0 && $schedule->startTime !== null && $schedule->endTime !== null) {
            return $this->futureWindowedIntervalTriggers($schedule, $now, $horizonEnd);
        }

        if ($schedule->intervalSec > 0) {
            return $this->futureIntervalTriggers(
                taskName: SchedulerRuntimeHelper::scheduleTaskLogName($schedule->zoneId, $schedule->taskType),
                intervalSec: $schedule->intervalSec,
                lastRunByTaskName: $lastRunByTaskName,
                now: $now,
                horizonEnd: $horizonEnd,
            );
        }

        return [];
    }

    /**
     * @return array<int, CarbonImmutable>
     */
    private function futureDailyTriggers(string $time, CarbonImmutable $now, CarbonImmutable $horizonEnd): array
    {
        $triggers = [];
        for ($cursor = $now->startOfDay(); $cursor->lte($horizonEnd->startOfDay()); $cursor = $cursor->addDay()) {
            $candidate = CarbonImmutable::createFromFormat(
                'Y-m-d H:i:s',
                $cursor->toDateString().' '.$time,
                'UTC',
            );

            if ($candidate->lt($now) || $candidate->gt($horizonEnd)) {
                continue;
            }

            $triggers[] = $candidate;
        }

        return $triggers;
    }

    /**
     * @param  array<string, CarbonImmutable>  $lastRunByTaskName
     * @return array<int, CarbonImmutable>
     */
    private function futureIntervalTriggers(
        string $taskName,
        int $intervalSec,
        array $lastRunByTaskName,
        CarbonImmutable $now,
        CarbonImmutable $horizonEnd,
    ): array {
        if ($intervalSec <= 0) {
            return [];
        }

        $anchor = $lastRunByTaskName[$taskName] ?? null;
        $nextAt = $anchor instanceof CarbonImmutable
            ? $anchor->addSeconds($intervalSec)
            : $now;

        if ($nextAt->lt($now)) {
            $elapsed = $now->diffInSeconds($nextAt);
            $steps = (int) floor($elapsed / $intervalSec);
            $nextAt = $nextAt->addSeconds($steps * $intervalSec);
            if ($nextAt->lt($now)) {
                $nextAt = $nextAt->addSeconds($intervalSec);
            }
        }

        $triggers = [];
        for ($cursor = $nextAt; $cursor->lte($horizonEnd); $cursor = $cursor->addSeconds($intervalSec)) {
            if ($cursor->gte($now)) {
                $triggers[] = $cursor;
            }
        }

        return $triggers;
    }

    /**
     * @return array<int, CarbonImmutable>
     */
    private function futureWindowedIntervalTriggers(
        ScheduleItem $schedule,
        CarbonImmutable $now,
        CarbonImmutable $horizonEnd,
    ): array {
        $triggers = [];
        for ($day = $now->startOfDay(); $day->lte($horizonEnd->startOfDay()); $day = $day->addDay()) {
            $windowStart = CarbonImmutable::createFromFormat(
                'Y-m-d H:i:s',
                $day->toDateString().' '.$schedule->startTime,
                'UTC',
            );
            $windowEnd = CarbonImmutable::createFromFormat(
                'Y-m-d H:i:s',
                $day->toDateString().' '.$schedule->endTime,
                'UTC',
            );
            if ($windowEnd->lt($windowStart)) {
                $windowEnd = $windowEnd->addDay();
            }

            for ($cursor = $windowStart; $cursor->lte($windowEnd); $cursor = $cursor->addSeconds($schedule->intervalSec)) {
                if ($cursor->lt($now) || $cursor->gt($horizonEnd)) {
                    continue;
                }

                $triggers[] = $cursor;
            }
        }

        return $triggers;
    }

    /**
     * @param  array<int, array<string, mixed>>  $planWindows
     * @return array<string, mixed>
     */
    private function capabilitiesForZone(Zone $zone, array $planWindows): array
    {
        $plannedTaskTypes = array_values(array_unique(array_map(
            static fn (array $window): string => (string) ($window['task_type'] ?? ''),
            $planWindows,
        )));
        $plannedTaskTypes = array_values(array_filter($plannedTaskTypes, static fn (string $value): bool => $value !== ''));

        return [
            'executable_task_types' => $zone->automation_runtime === 'ae3' ? ['irrigation'] : $plannedTaskTypes,
            'planned_task_types' => $plannedTaskTypes,
            'diagnostics_available' => true,
        ];
    }

    /**
     * @param  array<int, array<string, mixed>>  $planWindows
     * @param  array<string, mixed>  $capabilities
     * @return array<string, array<string, mixed>>
     */
    private function buildLaneMap(array $planWindows, array $capabilities): array
    {
        $laneMap = [];
        foreach ($planWindows as $window) {
            $taskType = (string) ($window['task_type'] ?? '');
            if ($taskType === '') {
                continue;
            }

            if (! isset($laneMap[$taskType])) {
                $laneMap[$taskType] = [
                    'task_type' => $taskType,
                    'label' => $this->taskTypeLabel($taskType),
                    'mode' => (string) ($window['mode'] ?? 'schedule'),
                    'enabled' => true,
                    'available' => true,
                    'executable' => in_array($taskType, (array) ($capabilities['executable_task_types'] ?? []), true),
                ];
            }
        }

        return $laneMap;
    }

    /**
     * @return array<string, mixed>
     */
    private function buildControlSnapshot(Zone $zone, CarbonImmutable $now): array
    {
        $controlMode = 'auto';
        $allowedManualSteps = [];

        try {
            $cfg = $this->runtimeConfig->schedulerConfig();
            $apiUrl = rtrim((string) ($cfg['api_url'] ?? 'http://automation-engine:9405'), '/');
            $timeout = (float) ($cfg['timeout_sec'] ?? 2.0);

            /** @var Response $response */
            $response = Http::acceptJson()
                ->timeout($timeout)
                ->get("{$apiUrl}/zones/{$zone->id}/control-mode");

            if ($response->successful()) {
                $payload = $response->json();
                if (is_array($payload)) {
                    $data = is_array($payload['data'] ?? null) ? $payload['data'] : $payload;
                    $rawControlMode = strtolower(trim((string) ($data['control_mode'] ?? 'auto')));
                    if (in_array($rawControlMode, ['auto', 'semi', 'manual'], true)) {
                        $controlMode = $rawControlMode;
                    }
                    $allowedManualSteps = isset($data['allowed_manual_steps']) && is_array($data['allowed_manual_steps'])
                        ? array_values($data['allowed_manual_steps'])
                        : [];
                }
            }
        } catch (ConnectionException|\Throwable $e) {
            Log::warning('ScheduleWorkspaceService: control-mode snapshot unavailable, using fallback', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);
        }

        return [
            'automation_runtime' => (string) ($zone->automation_runtime ?? 'ae3'),
            'control_mode' => $controlMode,
            'allowed_manual_steps' => $allowedManualSteps,
            'bundle_revision' => $this->bundleRevisionForZone($zone->id),
            'generated_at' => SchedulerRuntimeHelper::toIso($now),
            'timezone' => (string) ($zone->greenhouse?->timezone ?? config('app.timezone', 'UTC')),
        ];
    }

    private function bundleRevisionForZone(int $zoneId): ?string
    {
        if (! \Illuminate\Support\Facades\Schema::hasTable('automation_effective_bundles')) {
            return null;
        }

        $row = \Illuminate\Support\Facades\DB::table('automation_effective_bundles')
            ->where('scope_type', 'zone')
            ->where('scope_id', $zoneId)
            ->first(['bundle_revision']);

        return is_object($row) && is_string($row->bundle_revision ?? null)
            ? trim((string) $row->bundle_revision)
            : null;
    }

    private function publicTaskType(string $taskType): string
    {
        $normalized = strtolower(trim($taskType));

        return $normalized === 'ventilation' ? 'climate' : $normalized;
    }

    private function taskTypeLabel(string $taskType): string
    {
        return match ($this->publicTaskType($taskType)) {
            'irrigation' => 'Полив',
            'lighting' => 'Свет',
            'climate' => 'Климат',
            'solution_change' => 'Смена раствора',
            'diagnostics' => 'Диагностика',
            'mist' => 'Туман',
            default => ucfirst($this->publicTaskType($taskType)),
        };
    }

    private function scheduleMode(ScheduleItem $schedule): string
    {
        if ($schedule->intervalSec > 0 && $schedule->startTime !== null && $schedule->endTime !== null) {
            return 'window_interval';
        }
        if ($schedule->intervalSec > 0) {
            return 'interval';
        }

        return 'schedule';
    }
}
