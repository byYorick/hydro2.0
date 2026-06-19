<?php

namespace App\Services\AutomationScheduler;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneManualSchedule;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Validation\ValidationException;

class ManualScheduleService
{
    public const AE3_EXECUTABLE_TASK_TYPES = [
        'irrigation',
        'lighting',
        'diagnostics',
    ];

    public const ALLOWED_TASK_TYPES = [
        'irrigation',
        'lighting',
        'diagnostics',
        'ventilation',
        'mist',
        'solution_change',
    ];

    public const ALLOWED_SCHEDULE_KINDS = [
        'time',
        'interval',
        'window',
        'once',
    ];

    private const DAY_LABELS = [
        1 => 'Пн',
        2 => 'Вт',
        3 => 'Ср',
        4 => 'Чт',
        5 => 'Пт',
        6 => 'Сб',
        7 => 'Вс',
    ];

    public function __construct(
        private readonly ManualScheduleItemBuilder $itemBuilder,
        private readonly ActiveTaskStore $activeTaskStore,
    ) {}

    /**
     * @return array<int, array<string, mixed>>
     */
    public function listForZone(int $zoneId): array
    {
        if ($zoneId <= 0) {
            return [];
        }

        return ZoneManualSchedule::query()
            ->where('zone_id', $zoneId)
            ->orderByDesc('enabled')
            ->orderBy('task_type')
            ->orderBy('id')
            ->get()
            ->map(fn (ZoneManualSchedule $row): array => $this->serialize($row))
            ->values()
            ->all();
    }

    /**
     * @param  array<string, mixed>  $data
     */
    public function create(Zone $zone, array $data, ?User $actor = null): ZoneManualSchedule
    {
        $normalized = $this->normalizeInput($data);
        $normalized = $this->applyKindFieldExclusivity($normalized);
        $this->assertKindShape($normalized);
        $this->assertExecutableTaskTypeForZone($zone, (string) $normalized['task_type']);

        return DB::transaction(function () use ($zone, $normalized, $actor): ZoneManualSchedule {
            $schedule = ZoneManualSchedule::query()->create([
                'zone_id' => $zone->id,
                'task_type' => $normalized['task_type'],
                'schedule_kind' => $normalized['schedule_kind'],
                'time_at' => $normalized['time_at'],
                'interval_sec' => $normalized['interval_sec'],
                'window_start' => $normalized['window_start'],
                'window_end' => $normalized['window_end'],
                'days_of_week' => $normalized['days_of_week'],
                'run_at' => $normalized['run_at'],
                'payload' => $normalized['payload'],
                'label' => $normalized['label'],
                'enabled' => $normalized['enabled'],
                'created_by' => $actor?->id,
            ]);

            Log::info('zone_manual_schedule_created', [
                'zone_id' => $zone->id,
                'manual_schedule_id' => $schedule->id,
                'task_type' => $schedule->task_type,
                'schedule_kind' => $schedule->schedule_kind,
                'created_by' => $actor?->id,
            ]);

            return $schedule->fresh();
        });
    }

    /**
     * @param  array<string, mixed>  $data
     */
    public function update(ZoneManualSchedule $schedule, array $data): ZoneManualSchedule
    {
        $zone = $schedule->relationLoaded('zone')
            ? $schedule->zone
            : Zone::query()->find($schedule->zone_id);
        if (! $zone instanceof Zone) {
            throw ValidationException::withMessages([
                'zone_id' => 'Зона для расписания не найдена.',
            ]);
        }

        $previousRunAt = $schedule->run_at?->utc();
        $normalized = $this->normalizeInput(array_merge($this->serialize($schedule), $data));
        $normalized = $this->applyKindFieldExclusivity($normalized);
        $this->assertKindShape($normalized, forUpdate: true);
        $this->assertExecutableTaskTypeForZone($zone, (string) $normalized['task_type']);
        $this->assertNoActiveDispatchConflict($schedule, $normalized);

        $resetOnceDispatchState = false;
        if (
            $normalized['schedule_kind'] === 'once'
            && $normalized['run_at'] instanceof CarbonImmutable
            && $normalized['run_at']->gt(SchedulerRuntimeHelper::nowUtc())
        ) {
            if ($previousRunAt === null || ! $normalized['run_at']->equalTo($previousRunAt)) {
                $resetOnceDispatchState = true;
            }
        }

        if (
            $normalized['schedule_kind'] === 'once'
            && (bool) $normalized['enabled']
            && $schedule->last_dispatched_at !== null
            && ! $resetOnceDispatchState
        ) {
            throw ValidationException::withMessages([
                'enabled' => 'Для повторного включения однократного расписания укажите новый run_at в будущем.',
            ]);
        }

        $schedule->fill([
            'task_type' => $normalized['task_type'],
            'schedule_kind' => $normalized['schedule_kind'],
            'time_at' => $normalized['time_at'],
            'interval_sec' => $normalized['interval_sec'],
            'window_start' => $normalized['window_start'],
            'window_end' => $normalized['window_end'],
            'days_of_week' => $normalized['days_of_week'],
            'run_at' => $normalized['run_at'],
            'payload' => $normalized['payload'],
            'label' => $normalized['label'],
            'enabled' => $normalized['enabled'],
        ]);

        if ($resetOnceDispatchState) {
            $schedule->last_dispatched_at = null;
        }

        $schedule->save();

        Log::info('zone_manual_schedule_updated', [
            'zone_id' => $schedule->zone_id,
            'manual_schedule_id' => $schedule->id,
            'task_type' => $schedule->task_type,
            'schedule_kind' => $schedule->schedule_kind,
            'reset_once_dispatch_state' => $resetOnceDispatchState,
        ]);

        return $schedule->fresh();
    }

    public function delete(ZoneManualSchedule $schedule): void
    {
        $this->assertDeletable($schedule);

        Log::info('zone_manual_schedule_deleted', [
            'zone_id' => $schedule->zone_id,
            'manual_schedule_id' => $schedule->id,
            'task_type' => $schedule->task_type,
            'schedule_kind' => $schedule->schedule_kind,
        ]);

        $schedule->delete();
    }

    public function markDispatched(ZoneManualSchedule $schedule, CarbonImmutable $dispatchedAt): bool
    {
        $values = [
            'last_dispatched_at' => $dispatchedAt,
            'updated_at' => $dispatchedAt,
        ];
        if ($schedule->schedule_kind === 'once') {
            $values['enabled'] = false;
        }

        $updated = ZoneManualSchedule::query()
            ->whereKey($schedule->id)
            ->whereNull('last_dispatched_at')
            ->update($values);

        return $updated === 1;
    }

    /**
     * @return array<int, ScheduleItem>
     */
    public function buildScheduleItemsForZone(int $zoneId): array
    {
        return $this->itemBuilder->buildForZone($zoneId);
    }

    /**
     * @param  array<int, int>  $zoneIds
     * @return array<int, array<int, ScheduleItem>>
     */
    public function buildScheduleItemsForZones(array $zoneIds): array
    {
        return $this->itemBuilder->buildForZones($zoneIds);
    }

    /**
     * @return array<string, mixed>
     */
    public function serialize(ZoneManualSchedule $schedule): array
    {
        $daysOfWeek = ScheduleSpecHelper::normalizeDaysOfWeek($schedule->days_of_week);

        return [
            'id' => (int) $schedule->id,
            'zone_id' => (int) $schedule->zone_id,
            'task_type' => (string) $schedule->task_type,
            'schedule_kind' => (string) $schedule->schedule_kind,
            'time_at' => $this->formatTimeField($schedule->time_at),
            'interval_sec' => $schedule->interval_sec !== null ? (int) $schedule->interval_sec : null,
            'window_start' => $this->formatTimeField($schedule->window_start),
            'window_end' => $this->formatTimeField($schedule->window_end),
            'days_of_week' => $daysOfWeek,
            'run_at' => $schedule->run_at?->utc()->toIso8601String(),
            'last_dispatched_at' => $schedule->last_dispatched_at?->utc()->toIso8601String(),
            'payload' => is_array($schedule->payload) ? $schedule->payload : [],
            'label' => $schedule->label,
            'enabled' => (bool) $schedule->enabled,
            'created_by' => $schedule->created_by !== null ? (int) $schedule->created_by : null,
            'created_at' => $schedule->created_at?->toIso8601String(),
            'updated_at' => $schedule->updated_at?->toIso8601String(),
            'summary' => $this->buildSummary($schedule),
        ];
    }

    /**
     * @param  array<string, mixed>  $data
     * @return array<string, mixed>
     */
    private function normalizeInput(array $data): array
    {
        $taskType = strtolower(trim((string) ($data['task_type'] ?? '')));
        $scheduleKind = strtolower(trim((string) ($data['schedule_kind'] ?? '')));

        if (! in_array($taskType, self::ALLOWED_TASK_TYPES, true)) {
            throw ValidationException::withMessages([
                'task_type' => 'Допустимые типы: '.implode(', ', self::ALLOWED_TASK_TYPES).'.',
            ]);
        }

        if (! in_array($scheduleKind, self::ALLOWED_SCHEDULE_KINDS, true)) {
            throw ValidationException::withMessages([
                'schedule_kind' => 'Допустимые виды: '.implode(', ', self::ALLOWED_SCHEDULE_KINDS).'.',
            ]);
        }

        $payload = $this->normalizePayload($taskType, is_array($data['payload'] ?? null) ? $data['payload'] : []);

        $label = isset($data['label']) ? trim((string) $data['label']) : null;
        if ($label === '') {
            $label = null;
        }

        $runAt = null;
        if ($scheduleKind === 'once') {
            $runAt = ScheduleSpecHelper::parseRunAt($data['run_at'] ?? null);
        }

        return [
            'task_type' => $taskType,
            'schedule_kind' => $scheduleKind,
            'time_at' => ScheduleSpecHelper::parseTimeSpec((string) ($data['time_at'] ?? '')),
            'interval_sec' => ScheduleSpecHelper::safePositiveInt($data['interval_sec'] ?? null) ?: null,
            'window_start' => ScheduleSpecHelper::parseTimeSpec((string) ($data['window_start'] ?? '')),
            'window_end' => ScheduleSpecHelper::parseTimeSpec((string) ($data['window_end'] ?? '')),
            'days_of_week' => ScheduleSpecHelper::normalizeDaysOfWeek($data['days_of_week'] ?? null),
            'run_at' => $runAt,
            'payload' => $payload,
            'label' => $label,
            'enabled' => array_key_exists('enabled', $data) ? (bool) $data['enabled'] : true,
        ];
    }

    /**
     * @param  array<string, mixed>  $payload
     * @return array<string, mixed>
     */
    private function normalizePayload(string $taskType, array $payload): array
    {
        return match ($taskType) {
            'irrigation' => $this->normalizeIrrigationPayload($payload),
            default => [],
        };
    }

    /**
     * @param  array<string, mixed>  $payload
     * @return array<string, int>
     */
    private function normalizeIrrigationPayload(array $payload): array
    {
        $durationSec = ScheduleSpecHelper::safePositiveInt($payload['duration_sec'] ?? null);
        if ($durationSec <= 0) {
            return [];
        }

        if ($durationSec < 10 || $durationSec > 86400) {
            throw ValidationException::withMessages([
                'payload.duration_sec' => 'duration_sec должен быть от 10 до 86400 секунд.',
            ]);
        }

        return ['duration_sec' => $durationSec];
    }

    /**
     * @param  array<string, mixed>  $normalized
     */
    private function assertKindShape(array $normalized, bool $forUpdate = false): void
    {
        $kind = (string) $normalized['schedule_kind'];

        if ($kind === 'time' && $normalized['time_at'] === null) {
            throw ValidationException::withMessages([
                'time_at' => 'Для schedule_kind=time укажите time_at в формате HH:MM.',
            ]);
        }

        if ($kind === 'interval') {
            $intervalSec = ScheduleSpecHelper::safePositiveInt($normalized['interval_sec'] ?? null);
            if ($intervalSec < 60) {
                throw ValidationException::withMessages([
                    'interval_sec' => 'Для schedule_kind=interval interval_sec должен быть не меньше 60.',
                ]);
            }
            if ($intervalSec > 86400) {
                throw ValidationException::withMessages([
                    'interval_sec' => 'Для schedule_kind=interval interval_sec не должен превышать 86400.',
                ]);
            }
        }

        if ($kind === 'window') {
            if ($normalized['window_start'] === null || $normalized['window_end'] === null) {
                throw ValidationException::withMessages([
                    'window_start' => 'Для schedule_kind=window укажите window_start и window_end.',
                ]);
            }
        }

        if ($kind === 'once') {
            if (! $normalized['run_at'] instanceof CarbonImmutable) {
                throw ValidationException::withMessages([
                    'run_at' => 'Для schedule_kind=once укажите run_at (ISO 8601).',
                ]);
            }
            if (! $forUpdate && $normalized['run_at']->lte(SchedulerRuntimeHelper::nowUtc())) {
                throw ValidationException::withMessages([
                    'run_at' => 'Для schedule_kind=once run_at должен быть в будущем.',
                ]);
            }
        }
    }

    private function formatTimeField(mixed $value): ?string
    {
        if ($value === null) {
            return null;
        }

        $candidate = trim((string) $value);
        if ($candidate === '') {
            return null;
        }

        if (str_contains($candidate, ' ')) {
            $parts = explode(' ', $candidate);
            $candidate = (string) end($parts);
        }

        $parsed = ScheduleSpecHelper::parseTimeSpec($candidate);

        return $parsed !== null ? substr($parsed, 0, 5) : $candidate;
    }

    private function buildSummary(ZoneManualSchedule $schedule): string
    {
        $kind = strtolower(trim((string) $schedule->schedule_kind));
        $taskType = $this->taskTypeLabel((string) $schedule->task_type);
        $daysSuffix = $this->formatDaysSummary(ScheduleSpecHelper::normalizeDaysOfWeek($schedule->days_of_week));

        return match ($kind) {
            'time' => sprintf(
                '%s%s в %s',
                $taskType,
                $daysSuffix,
                $this->formatTimeField($schedule->time_at) ?? '—',
            ),
            'interval' => sprintf(
                '%s%s · %s',
                $taskType,
                $daysSuffix,
                $this->formatIntervalSummary((int) ($schedule->interval_sec ?? 0)),
            ),
            'window' => sprintf(
                '%s%s %s–%s',
                $taskType,
                $daysSuffix,
                $this->formatTimeField($schedule->window_start) ?? '—',
                $this->formatTimeField($schedule->window_end) ?? '—',
            ),
            'once' => sprintf(
                '%s · однократно %s UTC',
                $taskType,
                $schedule->run_at?->utc()->format('d.m.Y H:i') ?? '—',
            ),
            default => $taskType,
        };
    }

    private function taskTypeLabel(string $taskType): string
    {
        return match (strtolower(trim($taskType))) {
            'irrigation' => 'Полив',
            'lighting' => 'Свет',
            'ventilation' => 'Климат',
            'mist' => 'Туман',
            'solution_change' => 'Смена раствора',
            'diagnostics' => 'Диагностика',
            default => ucfirst($taskType),
        };
    }

    /**
     * @param  array<int, int>  $daysOfWeek
     */
    private function formatDaysSummary(array $daysOfWeek): string
    {
        if ($daysOfWeek === []) {
            return '';
        }

        $labels = array_map(
            static fn (int $day): string => self::DAY_LABELS[$day] ?? (string) $day,
            $daysOfWeek,
        );

        return ' · '.implode(', ', $labels);
    }

    private function formatIntervalSummary(int $intervalSec): string
    {
        if ($intervalSec <= 0) {
            return '—';
        }

        if ($intervalSec % 3600 === 0) {
            $hours = (int) ($intervalSec / 3600);

            return sprintf('каждые %d ч', $hours);
        }

        if ($intervalSec % 60 === 0) {
            $minutes = (int) ($intervalSec / 60);

            return sprintf('каждые %d мин', $minutes);
        }

        return sprintf('каждые %d с', $intervalSec);
    }

    /**
     * @param  array<string, mixed>  $normalized
     * @return array<string, mixed>
     */
    private function applyKindFieldExclusivity(array $normalized): array
    {
        $kind = (string) ($normalized['schedule_kind'] ?? '');

        if ($kind !== 'time') {
            $normalized['time_at'] = null;
        }
        if ($kind !== 'interval') {
            $normalized['interval_sec'] = null;
        }
        if ($kind !== 'window') {
            $normalized['window_start'] = null;
            $normalized['window_end'] = null;
        }
        if ($kind !== 'once') {
            $normalized['run_at'] = null;
        }
        if ($kind === 'once') {
            $normalized['days_of_week'] = [];
        }

        return $normalized;
    }

    private function assertExecutableTaskTypeForZone(Zone $zone, string $taskType): void
    {
        if ($zone->automation_runtime !== 'ae3') {
            return;
        }

        if (! in_array($taskType, self::AE3_EXECUTABLE_TASK_TYPES, true)) {
            throw ValidationException::withMessages([
                'task_type' => 'Для зон AE3 допустимы только: '.implode(', ', self::AE3_EXECUTABLE_TASK_TYPES).'.',
            ]);
        }
    }

    /**
     * @param  array<string, mixed>  $normalized
     */
    private function assertNoActiveDispatchConflict(ZoneManualSchedule $schedule, array $normalized): void
    {
        $taskTypeChanged = (string) $normalized['task_type'] !== (string) $schedule->task_type;
        $kindChanged = (string) $normalized['schedule_kind'] !== (string) $schedule->schedule_kind;
        if (! $taskTypeChanged && ! $kindChanged) {
            return;
        }

        $currentItem = $this->itemBuilder->toScheduleItem($schedule);
        if ($currentItem === null) {
            return;
        }

        $active = $this->activeTaskStore->findActiveByScheduleKey(
            $currentItem->scheduleKey,
            SchedulerRuntimeHelper::nowUtc(),
        );
        if ($active !== null) {
            throw ValidationException::withMessages([
                'schedule_kind' => 'Нельзя менять тип или вид расписания, пока выполняется связанная задача планировщика.',
            ]);
        }
    }

    private function assertDeletable(ZoneManualSchedule $schedule): void
    {
        $item = $this->itemBuilder->toScheduleItem($schedule);
        if ($item === null) {
            return;
        }

        $active = $this->activeTaskStore->findActiveByScheduleKey(
            $item->scheduleKey,
            SchedulerRuntimeHelper::nowUtc(),
        );
        if ($active !== null) {
            throw ValidationException::withMessages([
                'manual_schedule' => 'Нельзя удалить расписание, пока выполняется связанная задача планировщика.',
            ]);
        }
    }
}
