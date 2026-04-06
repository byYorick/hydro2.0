<?php

namespace App\Services\AutomationScheduler;

use Carbon\CarbonImmutable;

class ZoneScheduleItemBuilder
{
    public function __construct(
        private readonly LightingScheduleParser $lightingScheduleParser,
    ) {}

    /**
     * @param  array<string, mixed>  $targets
     * @return array<int, ScheduleItem>
     */
    public function buildSchedulesForZone(int $zoneId, array $targets, ?CarbonImmutable $nowUtc = null): array
    {
        $schedules = [];
        $nowUtc ??= SchedulerRuntimeHelper::nowUtc();

        $irrigation = is_array($targets['irrigation'] ?? null) ? $targets['irrigation'] : [];
        $irrigationSchedule = $targets['irrigation_schedule'] ?? ($irrigation['schedule'] ?? null);
        if ($this->isTaskScheduleEnabled('irrigation', $targets, $irrigation)) {
            foreach ($this->buildGenericTaskSchedules($zoneId, 'irrigation', $irrigation, $irrigationSchedule) as $schedule) {
                $schedules[] = $schedule;
            }
        }

        $lighting = is_array($targets['lighting'] ?? null) ? $targets['lighting'] : [];
        if ($this->isTaskScheduleEnabled('lighting', $targets, $lighting)) {
            $lightingSchedule = $targets['lighting_schedule'] ?? null;
            foreach ($this->lightingScheduleParser->parse($zoneId, $lighting, $lightingSchedule, $nowUtc) as $schedule) {
                $schedules[] = $schedule;
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
            foreach ($this->buildGenericTaskSchedules($zoneId, (string) $taskType, (array) $config, $source) as $schedule) {
                $schedules[] = $schedule;
            }
        }

        return $schedules;
    }

    /**
     * @param  array<string, mixed>  $config
     * @return array<int, ScheduleItem>
     */
    private function buildGenericTaskSchedules(
        int $zoneId,
        string $taskType,
        array $config,
        mixed $scheduleSpec,
    ): array {
        $schedules = [];

        $taskPayload = $taskType === 'irrigation' ? $this->irrigationSchedulePayload($config) : [];

        foreach (ScheduleSpecHelper::extractTimeSpecs($scheduleSpec) as $timeSpec) {
            $schedules[] = new ScheduleItem(
                zoneId: $zoneId,
                taskType: $taskType,
                time: $timeSpec,
                startTime: null,
                endTime: null,
                intervalSec: 0,
                payload: $taskPayload,
            );
        }

        $intervalSec = ScheduleSpecHelper::safePositiveInt(
            $config['interval_sec'] ?? ($config['every_sec'] ?? ($config['interval'] ?? null))
        );
        if ($intervalSec > 0) {
            $schedules[] = new ScheduleItem(
                zoneId: $zoneId,
                taskType: $taskType,
                intervalSec: $intervalSec,
                payload: $taskPayload,
            );
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

        $configEnabled = $this->coerceSubsystemEnabledFlag($config['enabled'] ?? null);
        if ($configEnabled === false) {
            return false;
        }

        return true;
    }

    /**
     * Payload для dispatch полива: `duration_sec` из effective targets передаётся в `ScheduleDispatcher`
     * как `requested_duration_sec` в `POST .../start-irrigation` (если задано положительное число).
     *
     * @param  array<string, mixed>  $config
     * @return array<string, mixed>
     */
    private function irrigationSchedulePayload(array $config): array
    {
        $durationSec = ScheduleSpecHelper::safePositiveInt($config['duration_sec'] ?? null);
        if ($durationSec > 0) {
            return ['duration_sec' => $durationSec];
        }

        return [];
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
        return $this->coerceSubsystemEnabledFlag($subsystem['enabled'] ?? null);
    }

    /**
     * То же согласование, что в EffectiveTargetsService::toBool: JSON/БД могут отдавать 0/1 или строки.
     */
    private function coerceSubsystemEnabledFlag(mixed $value): ?bool
    {
        if ($value === null) {
            return null;
        }

        if (is_bool($value)) {
            return $value;
        }

        if (is_int($value) || is_float($value)) {
            return ((int) $value) !== 0;
        }

        if (is_string($value)) {
            $normalized = strtolower(trim($value));
            if (in_array($normalized, ['1', 'true', 'yes', 'on'], true)) {
                return true;
            }
            if (in_array($normalized, ['0', 'false', 'no', 'off'], true)) {
                return false;
            }
        }

        return null;
    }
}
