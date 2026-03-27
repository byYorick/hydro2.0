<?php

namespace App\Services\AutomationScheduler;

use App\Models\Zone;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class SchedulerDiagnosticsService
{
    /**
     * @return array<string, mixed>
     */
    public function buildForZone(Zone $zone, int $taskLimit = 20, int $logLimit = 20): array
    {
        $now = SchedulerRuntimeHelper::nowUtc();
        $safeTaskLimit = max(1, min($taskLimit, 100));
        $safeLogLimit = max(1, min($logLimit, 100));

        $dispatcherTasks = $this->dispatcherTasks($zone->id, $safeTaskLimit);
        $recentLogs = $this->recentLogs($zone->id, $safeLogLimit);

        return [
            'zone_id' => $zone->id,
            'generated_at' => SchedulerRuntimeHelper::toIso($now),
            'sources' => [
                'dispatcher_tasks' => Schema::hasTable('laravel_scheduler_active_tasks'),
                'scheduler_logs' => Schema::hasTable('scheduler_logs'),
            ],
            'summary' => [
                'tracked_tasks_total' => count($dispatcherTasks),
                'active_tasks_total' => $this->countActiveTasks($dispatcherTasks),
                'overdue_tasks_total' => $this->countOverdueTasks($dispatcherTasks, $now),
                'stale_tasks_total' => $this->countStaleTasks($dispatcherTasks, $now),
                'recent_logs_total' => count($recentLogs),
                'last_log_at' => $recentLogs[0]['created_at'] ?? null,
            ],
            'dispatcher_tasks' => $dispatcherTasks,
            'recent_logs' => $recentLogs,
        ];
    }

    /**
     * @return array<int, array<string, mixed>>
     */
    private function dispatcherTasks(int $zoneId, int $limit): array
    {
        if (! Schema::hasTable('laravel_scheduler_active_tasks')) {
            return [];
        }

        return DB::table('laravel_scheduler_active_tasks')
            ->where('zone_id', $zoneId)
            ->orderByDesc('updated_at')
            ->orderByDesc('id')
            ->limit($limit)
            ->get([
                'task_id',
                'task_type',
                'schedule_key',
                'correlation_id',
                'status',
                'accepted_at',
                'due_at',
                'expires_at',
                'last_polled_at',
                'terminal_at',
                'updated_at',
                'details',
            ])
            ->map(function ($row): array {
                return [
                    'task_id' => (string) ($row->task_id ?? ''),
                    'task_type' => $this->resolveString($row->task_type ?? null),
                    'schedule_key' => $this->resolveString($row->schedule_key ?? null),
                    'correlation_id' => $this->resolveString($row->correlation_id ?? null),
                    'status' => $this->resolveString($row->status ?? null),
                    'accepted_at' => $this->toIso8601($row->accepted_at ?? null),
                    'due_at' => $this->toIso8601($row->due_at ?? null),
                    'expires_at' => $this->toIso8601($row->expires_at ?? null),
                    'last_polled_at' => $this->toIso8601($row->last_polled_at ?? null),
                    'terminal_at' => $this->toIso8601($row->terminal_at ?? null),
                    'updated_at' => $this->toIso8601($row->updated_at ?? null),
                    'details' => $this->normalizeJson($row->details ?? null),
                ];
            })
            ->values()
            ->all();
    }

    /**
     * @return array<int, array<string, mixed>>
     */
    private function recentLogs(int $zoneId, int $limit): array
    {
        if (! Schema::hasTable('scheduler_logs')) {
            return [];
        }

        return DB::table('scheduler_logs')
            ->whereRaw("details->>'zone_id' = ?", [(string) $zoneId])
            ->orderByDesc('created_at')
            ->orderByDesc('id')
            ->limit($limit)
            ->get([
                'id',
                'task_name',
                'status',
                'details',
                'created_at',
            ])
            ->map(function ($row): array {
                return [
                    'log_id' => (int) ($row->id ?? 0),
                    'task_name' => $this->resolveString($row->task_name ?? null),
                    'status' => $this->resolveString($row->status ?? null),
                    'created_at' => $this->toIso8601($row->created_at ?? null),
                    'details' => $this->normalizeJson($row->details ?? null),
                ];
            })
            ->values()
            ->all();
    }

    /**
     * @param  array<int, array<string, mixed>>  $dispatcherTasks
     */
    private function countActiveTasks(array $dispatcherTasks): int
    {
        return count(array_filter($dispatcherTasks, static function (array $task): bool {
            return in_array((string) ($task['status'] ?? ''), ['pending', 'accepted', 'running', 'waiting_command', 'claimed'], true)
                && empty($task['terminal_at']);
        }));
    }

    /**
     * @param  array<int, array<string, mixed>>  $dispatcherTasks
     */
    private function countOverdueTasks(array $dispatcherTasks, CarbonImmutable $now): int
    {
        return count(array_filter($dispatcherTasks, function (array $task) use ($now): bool {
            $dueAt = $this->parseCarbon($task['due_at'] ?? null);

            return $dueAt instanceof CarbonImmutable
                && $dueAt->lt($now)
                && empty($task['terminal_at']);
        }));
    }

    /**
     * @param  array<int, array<string, mixed>>  $dispatcherTasks
     */
    private function countStaleTasks(array $dispatcherTasks, CarbonImmutable $now): int
    {
        return count(array_filter($dispatcherTasks, function (array $task) use ($now): bool {
            $expiresAt = $this->parseCarbon($task['expires_at'] ?? null);

            return $expiresAt instanceof CarbonImmutable
                && $expiresAt->lt($now)
                && empty($task['terminal_at']);
        }));
    }

    /**
     * @return array<string, mixed>
     */
    private function normalizeJson(mixed $value): array
    {
        if (is_array($value)) {
            return $value;
        }

        if (is_string($value) && trim($value) !== '') {
            $decoded = json_decode($value, true);
            if (is_array($decoded)) {
                return $decoded;
            }
        }

        return [];
    }

    private function resolveString(mixed $value): ?string
    {
        if (! is_string($value)) {
            return null;
        }

        $normalized = trim($value);

        return $normalized !== '' ? $normalized : null;
    }

    private function toIso8601(mixed $value): ?string
    {
        $parsed = $this->parseCarbon($value);

        return $parsed?->utc()->toIso8601String();
    }

    private function parseCarbon(mixed $value): ?CarbonImmutable
    {
        if ($value === null || $value === '') {
            return null;
        }

        try {
            return CarbonImmutable::parse((string) $value);
        } catch (\Throwable) {
            return null;
        }
    }
}
