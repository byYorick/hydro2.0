<?php

namespace App\Http\Controllers\Concerns;

trait BuildsSchedulerTaskProcessView
{
    /**
     * @param  array<string,mixed>  $payload
     * @param  array<int, array<string,mixed>>  $timeline
     * @return array{process_state: array<string,mixed>, process_steps: array<int, array<string,mixed>>}
     */
    private function buildTaskProcessView(array $payload, array $timeline): array
    {
        $stepsByPhase = [];
        foreach (self::PROCESS_PHASE_SEQUENCE as $phaseCode) {
            $stepsByPhase[$phaseCode] = [
                'phase' => $phaseCode,
                'label' => self::PROCESS_PHASE_LABELS[$phaseCode] ?? $phaseCode,
                'status' => 'pending',
                'status_label' => $this->processStatusLabel('pending'),
                'started_at' => null,
                'updated_at' => null,
                'last_reason_code' => null,
                'last_event_type' => null,
            ];
        }

        $latestAction = null;
        foreach ($timeline as $event) {
            if (! is_array($event)) {
                continue;
            }

            $eventType = is_string($event['event_type'] ?? null) ? strtoupper(trim($event['event_type'])) : '';
            $reasonCode = is_string($event['reason_code'] ?? null) ? strtolower(trim($event['reason_code'])) : '';
            $runMode = is_string($event['run_mode'] ?? null) ? strtolower(trim($event['run_mode'])) : '';
            $at = $this->toIso8601($event['at'] ?? null);

            $phaseCode = $this->resolveProcessPhaseCode($eventType, $reasonCode, $runMode);
            if ($phaseCode === null || ! isset($stepsByPhase[$phaseCode])) {
                continue;
            }

            if ($at !== null && (
                ! is_array($latestAction)
                || strcmp((string) ($latestAction['at'] ?? ''), $at) <= 0
            )) {
                $latestAction = [
                    'event_type' => $eventType !== '' ? $eventType : null,
                    'reason_code' => $reasonCode !== '' ? $reasonCode : null,
                    'at' => $at,
                ];
            }

            $step = $stepsByPhase[$phaseCode];
            if ($step['started_at'] === null) {
                $step['started_at'] = $at;
            }
            $step['updated_at'] = $at;
            $step['last_reason_code'] = $reasonCode !== '' ? $reasonCode : null;
            $step['last_event_type'] = $eventType !== '' ? $eventType : null;

            $resolvedStatus = $this->resolveProcessStepStatus($eventType, $reasonCode);
            if ($resolvedStatus !== null) {
                $step['status'] = $resolvedStatus;
                $step['status_label'] = $this->processStatusLabel($resolvedStatus);
            } elseif ($step['status'] === 'pending') {
                $step['status'] = 'running';
                $step['status_label'] = $this->processStatusLabel('running');
            }

            $stepsByPhase[$phaseCode] = $step;
        }

        $taskStatus = strtolower(trim((string) ($payload['status'] ?? '')));
        $runMode = strtolower(trim((string) ($payload['run_mode'] ?? (($payload['result']['run_mode'] ?? '')))));
        if (in_array($taskStatus, ['failed', 'rejected', 'expired'], true)) {
            $failedPhase = $this->resolveCurrentPhaseCode($stepsByPhase) ?? 'setup_transition';
            $stepsByPhase[$failedPhase]['status'] = 'failed';
            $stepsByPhase[$failedPhase]['status_label'] = $this->processStatusLabel('failed');
            if ($stepsByPhase[$failedPhase]['updated_at'] === null) {
                $stepsByPhase[$failedPhase]['updated_at'] = $this->toIso8601($payload['updated_at'] ?? null);
            }
        }

        if ($taskStatus === 'completed') {
            if ($runMode === 'working') {
                $setupStep = $stepsByPhase['setup_transition'];
                if ($setupStep['status'] !== 'completed') {
                    $setupStep['status'] = 'completed';
                    $setupStep['status_label'] = $this->processStatusLabel('completed');
                    if ($setupStep['updated_at'] === null) {
                        $setupStep['updated_at'] = $this->toIso8601($payload['updated_at'] ?? null);
                    }
                }
                $stepsByPhase['setup_transition'] = $setupStep;
            }

            foreach (self::PROCESS_PHASE_SEQUENCE as $phaseCode) {
                if ($stepsByPhase[$phaseCode]['status'] === 'running') {
                    $stepsByPhase[$phaseCode]['status'] = 'completed';
                    $stepsByPhase[$phaseCode]['status_label'] = $this->processStatusLabel('completed');
                }
            }
        }

        $currentPhase = $this->resolveCurrentPhaseCode($stepsByPhase);
        $hasFailedStep = collect($stepsByPhase)->contains(static fn (array $step): bool => $step['status'] === 'failed');
        $hasRunningStep = collect($stepsByPhase)->contains(static fn (array $step): bool => $step['status'] === 'running');
        $allCompleted = collect($stepsByPhase)->every(static fn (array $step): bool => $step['status'] === 'completed');

        $processStatus = 'pending';
        if (in_array($taskStatus, ['failed', 'rejected', 'expired'], true) || $hasFailedStep) {
            $processStatus = 'failed';
        } elseif (in_array($taskStatus, ['accepted', 'running'], true) || $hasRunningStep) {
            $processStatus = 'running';
        } elseif ($taskStatus === 'completed' || $allCompleted) {
            $processStatus = 'completed';
        }

        $setupCompleted = $stepsByPhase['setup_transition']['status'] === 'completed';
        $processSteps = [];
        foreach (self::PROCESS_PHASE_SEQUENCE as $phaseCode) {
            $processSteps[] = $stepsByPhase[$phaseCode];
        }

        $processState = [
            'status' => $processStatus,
            'status_label' => $this->processStatusLabel($processStatus),
            'phase' => $currentPhase,
            'phase_label' => $currentPhase !== null ? (self::PROCESS_PHASE_LABELS[$currentPhase] ?? $currentPhase) : null,
            'is_setup_completed' => $setupCompleted,
            'is_work_mode' => $runMode === 'working' || $setupCompleted,
            'current_action' => $latestAction,
        ];

        return [
            'process_state' => $processState,
            'process_steps' => $processSteps,
        ];
    }

    private function resolveProcessPhaseCode(string $eventType, string $reasonCode, string $runMode): ?string
    {
        if ($reasonCode !== '' && in_array($reasonCode, self::PROCESS_CLEAN_FILL_REASON_CODES, true)) {
            return 'clean_fill';
        }
        if ($reasonCode !== '' && in_array($reasonCode, self::PROCESS_SOLUTION_FILL_REASON_CODES, true)) {
            return 'solution_fill';
        }
        if ($reasonCode !== '' && in_array($reasonCode, self::PROCESS_SETUP_TRANSITION_REASON_CODES, true)) {
            return 'setup_transition';
        }
        if ($reasonCode !== '' && in_array($reasonCode, self::PROCESS_PARALLEL_CORRECTION_REASON_CODES, true)) {
            return 'parallel_correction';
        }

        if (in_array($eventType, ['TANK_REFILL_STARTED', 'TANK_REFILL_COMPLETED', 'TANK_REFILL_TIMEOUT'], true)) {
            return 'clean_fill';
        }

        if (in_array($eventType, ['CYCLE_START_INITIATED', 'NODES_AVAILABILITY_CHECKED', 'TANK_LEVEL_CHECKED', 'TANK_LEVEL_STALE'], true)) {
            return 'clean_fill';
        }

        if (in_array($eventType, ['TASK_RECEIVED', 'TASK_STARTED', 'DECISION_MADE'], true)) {
            return 'clean_fill';
        }

        if ($runMode === 'working' && in_array($eventType, ['TASK_FINISHED', 'SCHEDULE_TASK_EXECUTION_FINISHED'], true)) {
            return 'setup_transition';
        }

        return null;
    }

    private function resolveProcessStepStatus(string $eventType, string $reasonCode): ?string
    {
        if (
            $reasonCode !== '' && in_array($reasonCode, self::PROCESS_FAIL_REASON_CODES, true)
            || in_array($eventType, ['TANK_REFILL_TIMEOUT', 'SCHEDULE_TASK_FAILED'], true)
        ) {
            return 'failed';
        }

        if (
            $reasonCode !== '' && in_array($reasonCode, self::PROCESS_SUCCESS_REASON_CODES, true)
            || in_array($eventType, ['TANK_REFILL_COMPLETED', 'TASK_FINISHED', 'SCHEDULE_TASK_COMPLETED', 'SCHEDULE_TASK_EXECUTION_FINISHED'], true)
        ) {
            return 'completed';
        }

        if (
            $reasonCode !== '' && in_array($reasonCode, self::PROCESS_RUNNING_REASON_CODES, true)
            || in_array($eventType, ['TASK_STARTED', 'SCHEDULE_TASK_EXECUTION_STARTED', 'TANK_REFILL_STARTED'], true)
        ) {
            return 'running';
        }

        return null;
    }

    /**
     * @param  array<string, array<string,mixed>>  $stepsByPhase
     */
    private function resolveCurrentPhaseCode(array $stepsByPhase): ?string
    {
        foreach (self::PROCESS_PHASE_SEQUENCE as $phaseCode) {
            if (($stepsByPhase[$phaseCode]['status'] ?? null) === 'running') {
                return $phaseCode;
            }
        }

        foreach (self::PROCESS_PHASE_SEQUENCE as $phaseCode) {
            if (($stepsByPhase[$phaseCode]['status'] ?? null) === 'failed') {
                return $phaseCode;
            }
        }

        $lastCompleted = null;
        foreach (self::PROCESS_PHASE_SEQUENCE as $phaseCode) {
            if (($stepsByPhase[$phaseCode]['status'] ?? null) === 'completed') {
                $lastCompleted = $phaseCode;
            }
        }

        return $lastCompleted;
    }

    private function processStatusLabel(string $status): string
    {
        return match ($status) {
            'running' => 'Выполняется',
            'completed' => 'Выполнено',
            'failed' => 'Ошибка',
            default => 'Ожидание',
        };
    }

    /**
     * @param  array<string,mixed>  $raw
     * @return array<string,mixed>
     */
    private function normalizeTaskPayload(array $raw, string $taskId, string $source): array
    {
        $result = is_array($raw['result'] ?? null) ? $raw['result'] : null;
        $actionRequired = $this->normalizeOptionalBool($raw['action_required'] ?? null);
        if ($actionRequired === null) {
            $actionRequired = $this->normalizeOptionalBool($result['action_required'] ?? null);
        }

        $decision = is_string($raw['decision'] ?? null) ? $raw['decision'] : null;
        if ($decision === null && is_string($result['decision'] ?? null)) {
            $decision = $result['decision'];
        }

        $reasonCode = is_string($raw['reason_code'] ?? null) ? $raw['reason_code'] : null;
        if ($reasonCode === null && is_string($result['reason_code'] ?? null)) {
            $reasonCode = $result['reason_code'];
        }

        $reason = is_string($raw['reason'] ?? null) ? $raw['reason'] : null;
        if ($reason === null && is_string($result['reason'] ?? null)) {
            $reason = $result['reason'];
        }

        $commandSubmitted = $this->normalizeOptionalBool($raw['command_submitted'] ?? null);
        if ($commandSubmitted === null) {
            $commandSubmitted = $this->normalizeOptionalBool($result['command_submitted'] ?? null);
        }

        $commandEffectConfirmed = $this->normalizeOptionalBool($raw['command_effect_confirmed'] ?? null);
        if ($commandEffectConfirmed === null) {
            $commandEffectConfirmed = $this->normalizeOptionalBool($result['command_effect_confirmed'] ?? null);
        }

        $commandsTotal = null;
        if (isset($raw['commands_total']) && is_numeric($raw['commands_total'])) {
            $commandsTotal = (int) $raw['commands_total'];
        } elseif (isset($result['commands_total']) && is_numeric($result['commands_total'])) {
            $commandsTotal = (int) $result['commands_total'];
        }

        $commandsEffectConfirmed = null;
        if (isset($raw['commands_effect_confirmed']) && is_numeric($raw['commands_effect_confirmed'])) {
            $commandsEffectConfirmed = (int) $raw['commands_effect_confirmed'];
        } elseif (isset($result['commands_effect_confirmed']) && is_numeric($result['commands_effect_confirmed'])) {
            $commandsEffectConfirmed = (int) $result['commands_effect_confirmed'];
        }

        $commandsFailed = null;
        if (isset($raw['commands_failed']) && is_numeric($raw['commands_failed'])) {
            $commandsFailed = (int) $raw['commands_failed'];
        } elseif (isset($result['commands_failed']) && is_numeric($result['commands_failed'])) {
            $commandsFailed = (int) $result['commands_failed'];
        }

        $executedSteps = is_array($raw['executed_steps'] ?? null) ? $raw['executed_steps'] : null;
        if ($executedSteps === null && is_array($result['executed_steps'] ?? null)) {
            $executedSteps = $result['executed_steps'];
        }

        $safetyFlags = is_array($raw['safety_flags'] ?? null) ? $raw['safety_flags'] : null;
        if ($safetyFlags === null && is_array($result['safety_flags'] ?? null)) {
            $safetyFlags = $result['safety_flags'];
        }

        $nextDueAt = is_string($raw['next_due_at'] ?? null) ? $raw['next_due_at'] : null;
        if ($nextDueAt === null && is_string($result['next_due_at'] ?? null)) {
            $nextDueAt = $result['next_due_at'];
        }

        $measurementsBeforeAfter = is_array($raw['measurements_before_after'] ?? null)
            ? $raw['measurements_before_after']
            : null;
        if ($measurementsBeforeAfter === null && is_array($result['measurements_before_after'] ?? null)) {
            $measurementsBeforeAfter = $result['measurements_before_after'];
        }

        $runMode = is_string($raw['run_mode'] ?? null) ? $raw['run_mode'] : null;
        if ($runMode === null && is_string($result['run_mode'] ?? null)) {
            $runMode = $result['run_mode'];
        }

        $retryAttempt = $this->normalizeOptionalInt($raw['retry_attempt'] ?? null);
        if ($retryAttempt === null) {
            $retryAttempt = $this->normalizeOptionalInt($result['retry_attempt'] ?? null);
        }

        $retryMaxAttempts = $this->normalizeOptionalInt($raw['retry_max_attempts'] ?? null);
        if ($retryMaxAttempts === null) {
            $retryMaxAttempts = $this->normalizeOptionalInt($result['retry_max_attempts'] ?? null);
        }

        $retryBackoffSec = $this->normalizeOptionalInt($raw['retry_backoff_sec'] ?? null);
        if ($retryBackoffSec === null) {
            $retryBackoffSec = $this->normalizeOptionalInt($result['retry_backoff_sec'] ?? null);
        }

        return [
            'task_id' => (string) ($raw['task_id'] ?? $taskId),
            'zone_id' => isset($raw['zone_id']) ? (int) $raw['zone_id'] : null,
            'task_type' => $raw['task_type'] ?? null,
            'status' => $this->normalizeSchedulerTaskStatus($raw['status'] ?? null),
            'created_at' => $raw['created_at'] ?? null,
            'updated_at' => $raw['updated_at'] ?? null,
            'scheduled_for' => $raw['scheduled_for'] ?? null,
            'due_at' => $raw['due_at'] ?? null,
            'expires_at' => $raw['expires_at'] ?? null,
            'correlation_id' => $raw['correlation_id'] ?? null,
            'result' => $result,
            'action_required' => $actionRequired,
            'decision' => $decision,
            'reason_code' => $reasonCode,
            'reason' => $reason,
            'command_submitted' => $commandSubmitted,
            'command_effect_confirmed' => $commandEffectConfirmed,
            'commands_total' => $commandsTotal,
            'commands_effect_confirmed' => $commandsEffectConfirmed,
            'commands_failed' => $commandsFailed,
            'executed_steps' => $executedSteps,
            'safety_flags' => $safetyFlags,
            'next_due_at' => $nextDueAt,
            'measurements_before_after' => $measurementsBeforeAfter,
            'run_mode' => $runMode,
            'retry_attempt' => $retryAttempt,
            'retry_max_attempts' => $retryMaxAttempts,
            'retry_backoff_sec' => $retryBackoffSec,
            'error' => is_string($raw['error'] ?? null) ? $raw['error'] : null,
            'error_code' => is_string($raw['error_code'] ?? null) ? $raw['error_code'] : null,
            'source' => $source,
        ];
    }

    /**
     * @param  mixed  $value
     */
    private function normalizeSchedulerTaskStatus($value): string
    {
        $status = strtolower(trim((string) $value));
        if ($status === 'pending' || $status === 'claimed') {
            return 'accepted';
        }
        if ($status === 'done') {
            return 'completed';
        }
        if ($status === 'error') {
            return 'failed';
        }
        if ($status === 'cancelled' || $status === 'canceled') {
            return 'rejected';
        }
        if ($status === 'timeout') {
            return 'expired';
        }

        return $status !== '' ? $status : 'unknown';
    }

    /**
     * @param  mixed  $value
     */
    private function toIso8601($value): ?string
    {
        if ($value instanceof \DateTimeInterface) {
            return $value->format(DATE_ATOM);
        }

        if (is_string($value) && $value !== '') {
            try {
                return (new \DateTimeImmutable($value))->format(DATE_ATOM);
            } catch (\Throwable $e) {
                return $value;
            }
        }

        return null;
    }

    /**
     * @param  mixed  $value
     */
    private function normalizeOptionalBool($value): ?bool
    {
        if (is_bool($value)) {
            return $value;
        }
        if (is_int($value)) {
            return $value === 1 ? true : ($value === 0 ? false : null);
        }
        if (is_string($value)) {
            $normalized = strtolower(trim($value));
            if ($normalized === 'true' || $normalized === '1') {
                return true;
            }
            if ($normalized === 'false' || $normalized === '0') {
                return false;
            }
        }

        return null;
    }

    /**
     * @param  mixed  $value
     */
    private function normalizeOptionalInt($value): ?int
    {
        if (is_int($value)) {
            return $value;
        }
        if (is_numeric($value)) {
            return (int) $value;
        }

        return null;
    }

    /**
     * @param  mixed  $rawDetails
     * @return array<string,mixed>
     */
    private function normalizeDetails($rawDetails): array
    {
        if (is_array($rawDetails)) {
            return $rawDetails;
        }

        if (is_string($rawDetails) && $rawDetails !== '') {
            $decoded = json_decode($rawDetails, true);

            return is_array($decoded) ? $decoded : [];
        }

        return [];
    }
}
