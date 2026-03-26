<?php

namespace App\Services;

class ZoneEventMessageFormatter
{
    public function __construct(
        private AlertLocalizationService $alertLocalization,
    ) {}

    /**
     * Сформировать человекочитаемое сообщение события зоны.
     */
    public function format(?string $type, mixed $details): string
    {
        $eventType = strtoupper((string) ($type ?? ''));
        $payload = $this->normalizeDetails($details);

        $explicitMessage = $this->extractExplicitMessage($eventType, $payload);
        if ($explicitMessage !== null) {
            return $explicitMessage;
        }

        if (str_starts_with($eventType, 'CYCLE_') && isset($payload['subsystems']) && is_array($payload['subsystems'])) {
            $subsystemsSummary = $this->formatSubsystemsSummary($payload['subsystems']);
            if ($subsystemsSummary !== null) {
                return $eventType === 'CYCLE_ADJUSTED'
                    ? 'Цикл скорректирован: '.$subsystemsSummary
                    : $subsystemsSummary;
            }
        }

        return match ($eventType) {
            'ALERT_CREATED' => $this->formatAlertCreated($payload),
            'ALERT_UPDATED' => $this->formatAlertUpdated($payload),
            'ALERT_RESOLVED' => $this->formatAlertResolved($payload),
            'WATER_LEVEL_LOW' => $this->formatWaterLevelLow($payload),
            'CYCLE_CREATED' => $this->formatCycleCreated($payload),
            'CYCLE_STARTED' => $this->formatCycleStarted($payload),
            'CYCLE_PAUSED' => $this->formatCyclePaused($payload),
            'CYCLE_RESUMED' => $this->formatCycleResumed($payload),
            'CYCLE_HARVESTED' => $this->formatCycleHarvested($payload),
            'CYCLE_ABORTED' => $this->formatCycleAborted($payload),
            'CYCLE_ADJUSTED' => $this->formatCycleAdjusted($payload),
            'CYCLE_PHASE_ADVANCED' => $this->formatCyclePhaseAdvanced($payload),
            'CYCLE_PHASE_SET' => $this->formatCyclePhaseSet($payload),
            'CYCLE_RECIPE_REVISION_CHANGED' => $this->formatCycleRecipeRevisionChanged($payload),
            'CYCLE_CONFIG' => $this->formatCycleConfig($payload),
            'PHASE_TRANSITION' => $this->formatPhaseTransition($payload),
            'RECIPE_PHASE_CHANGED' => $this->formatPhaseTransition($payload),
            'ZONE_COMMAND' => $this->formatZoneCommand($payload),
            'SCHEDULE_TASK_FAILED' => $this->formatScheduleTaskFailed($payload),
            'SELF_TASK_DISPATCH_RETRY_SCHEDULED' => $this->formatSelfTaskDispatchRetryScheduled($payload),
            'PH_CORRECTED' => $this->formatPhCorrected($payload),
            'EC_DOSING' => $this->formatEcDosing($payload),
            'PID_OUTPUT' => $this->formatPidOutput($payload),
            'PID_CONFIG_UPDATED' => $this->formatPidConfigUpdated($payload),
            'CORRECTION_STATE_TRANSITION' => $this->formatCorrectionStateTransition($payload),
            'CORRECTION_COMPLETE' => $this->formatCorrectionComplete($payload),
            'CORRECTION_EXHAUSTED' => $this->formatCorrectionExhausted($payload),
            'CORRECTION_LIMIT_POLICY_APPLIED' => $this->formatCorrectionLimitPolicyApplied($payload),
            'CORRECTION_ATTEMPT_CAP_IGNORED' => $this->formatCorrectionAttemptCapIgnored($payload),
            'CORRECTION_SKIPPED_DEAD_ZONE' => $this->formatCorrectionSkippedDeadZone($payload),
            'CORRECTION_SKIPPED_COOLDOWN' => $this->formatCorrectionSkippedCooldown($payload),
            'CORRECTION_SKIPPED_DOSE_DISCARDED' => $this->formatCorrectionSkippedDoseDiscarded($payload),
            'CORRECTION_SKIPPED_WATER_LEVEL' => $this->formatCorrectionSkippedWaterLevel($payload),
            'CORRECTION_SKIPPED_FRESHNESS' => $this->formatCorrectionSkippedFreshness($payload),
            'CORRECTION_SKIPPED_WINDOW_NOT_READY' => $this->formatCorrectionSkippedWindowNotReady($payload),
            'CORRECTION_OBSERVATION_EVALUATED' => $this->formatCorrectionObservationEvaluated($payload),
            'CORRECTION_NO_EFFECT' => $this->formatCorrectionNoEffect($payload),
            'RELAY_AUTOTUNE_COMPLETE', 'RELAY_AUTOTUNE_COMPLETED' => $this->formatRelayAutotuneComplete($payload),
            'PUMP_CALIBRATION_SAVED' => $this->formatPumpCalibrationSaved($payload),
            'PUMP_CALIBRATION_FINISHED' => $this->formatPumpCalibrationFinished($payload),
            'PUMP_CALIBRATION_RUN_SKIPPED' => $this->formatPumpCalibrationRunSkipped($payload),
            'PROCESS_CALIBRATION_SAVED' => $this->formatProcessCalibrationSaved($payload),
            'IRR_STATE_SNAPSHOT' => $this->formatIrrStateSnapshot($payload),
            'COMMAND_TIMEOUT' => $this->formatCommandTimeout($payload),
            'AE_STARTUP_PROBE_TIMEOUT' => $this->formatAeStartupProbeTimeout($payload),
            'CLEAN_FILL_COMPLETED' => 'Наполнение чистой водой завершено',
            'SOLUTION_FILL_COMPLETED' => 'Наполнение раствором завершено',
            'AE_TASK_STARTED' => $this->formatAeTaskStarted($payload),
            'AE_TASK_COMPLETED' => $this->formatAeTaskCompleted($payload),
            'AE_TASK_FAILED' => $this->formatAeTaskFailed($payload),
            'ALERT_TRIGGERED' => $this->formatAlertTriggered($payload),
            'NODE_CONNECTED' => $this->formatNodeEvent($payload, 'подключился'),
            'NODE_DISCONNECTED' => $this->formatNodeEvent($payload, 'отключился'),
            'AUTO_MODE_ENABLED' => 'Авторежим включён',
            'AUTO_MODE_DISABLED' => 'Авторежим выключен',
            'MANUAL_INTERVENTION' => $this->formatManualIntervention($payload),
            'SETTINGS_CHANGED' => 'Настройки изменены',
            'AUTOMATION_LOGIC_PROFILE_UPDATED' => 'Профиль автоматики обновлён',
            'IRRIGATION_START' => 'Полив запущен',
            'IRRIGATION_STOP' => 'Полив остановлен',
            'CALIBRATION_STARTED' => $this->formatCalibrationEvent($payload, 'Калибровка запущена'),
            'CALIBRATION_COMPLETED' => $this->formatCalibrationEvent($payload, 'Калибровка завершена'),
            'RECIPE_STARTED' => $this->formatRecipeEvent($payload, 'Рецепт запущен'),
            'RECIPE_COMPLETED' => $this->formatRecipeEvent($payload, 'Рецепт завершён'),
            'HARVEST_STARTED' => 'Сбор урожая начат',
            'HARVEST_COMPLETED' => 'Сбор урожая завершён',
            'PHASE_CHANGE' => $this->formatPhaseChange($payload),
            default => $type ?: '',
        };
    }

    /**
     * @return array<string, mixed>
     */
    private function normalizeDetails(mixed $details): array
    {
        if (is_array($details)) {
            return $details;
        }

        if (is_string($details) && $details !== '') {
            $decoded = json_decode($details, true);

            return is_array($decoded) ? $decoded : [];
        }

        return [];
    }

    private function extractExplicitMessage(string $eventType, array $details): ?string
    {
        $direct = $this->toStringOrNull($details['message'] ?? null)
            ?? $this->toStringOrNull($details['msg'] ?? null);

        $alertLikeEvents = [
            'ALERT_CREATED',
            'ALERT_UPDATED',
            'ALERT_RESOLVED',
            'AE_TASK_FAILED',
        ];

        if ($direct !== null) {
            if (in_array($eventType, $alertLikeEvents, true)) {
                return $this->localizeAlertPayloadMessage($details, $direct);
            }

            return $direct;
        }

        if (isset($details['details']) && is_array($details['details'])) {
            $nested = $this->toStringOrNull($details['details']['message'] ?? null)
                ?? $this->toStringOrNull($details['details']['msg'] ?? null);

            if ($nested !== null) {
                if (in_array($eventType, $alertLikeEvents, true)) {
                    return $this->localizeAlertPayloadMessage($details, $nested);
                }

                return $nested;
            }
        }

        return null;
    }

    /**
     * @param array<string, mixed> $details
     */
    private function localizeAlertPayloadMessage(array $details, string $fallback): string
    {
        $presentation = $this->alertLocalization->present(
            code: $this->toStringOrNull($details['code'] ?? null)
                ?? $this->toStringOrNull($details['error_code'] ?? null)
                ?? $this->toStringOrNull($details['alert_code'] ?? null),
            type: $this->toStringOrNull($details['alert_type'] ?? null)
                ?? $this->toStringOrNull($details['type'] ?? null),
            details: $details,
            source: $this->toStringOrNull($details['source'] ?? null),
        );

        return trim($presentation['message']) !== '' ? $presentation['message'] : $fallback;
    }

    private function formatAlertCreated(array $details): string
    {
        $code = $this->toStringOrNull($details['code'] ?? null)
            ?? $this->toStringOrNull($details['alert_type'] ?? null)
            ?? $this->toStringOrNull($details['type'] ?? null)
            ?? 'UNKNOWN';

        $parts = [];

        $alertType = $this->toStringOrNull($details['type'] ?? null);
        if ($alertType !== null && $alertType !== $code) {
            $parts[] = "тип {$alertType}";
        }

        $source = $this->toStringOrNull($details['source'] ?? null);
        if ($source !== null) {
            $parts[] = "источник {$source}";
        }

        $waterLevelContext = $this->formatWaterLevelContext($details);
        if ($waterLevelContext !== null) {
            $parts[] = $waterLevelContext;
        }

        $suffix = $parts !== [] ? ' ('.implode(', ', $parts).')' : '';

        return "Создан алерт {$code}{$suffix}";
    }

    private function formatAlertUpdated(array $details): string
    {
        $code = $this->toStringOrNull($details['code'] ?? null)
            ?? $this->toStringOrNull($details['alert_type'] ?? null)
            ?? 'UNKNOWN';

        $count = $details['error_count'] ?? $details['count'] ?? null;
        if (is_numeric($count)) {
            return sprintf('Алерт %s обновлён (повторений: %d)', $code, (int) $count);
        }

        return "Алерт {$code} обновлён";
    }

    private function formatAlertResolved(array $details): string
    {
        $code = $this->toStringOrNull($details['code'] ?? null)
            ?? $this->toStringOrNull($details['alert_type'] ?? null)
            ?? $this->toStringOrNull($details['alert_code'] ?? null)
            ?? 'UNKNOWN';

        $resolvedAt = $this->toStringOrNull($details['resolved_at'] ?? null);
        if ($resolvedAt !== null) {
            return "Алерт {$code} закрыт ({$resolvedAt})";
        }

        return "Алерт {$code} закрыт";
    }

    private function formatCycleCreated(array $details): string
    {
        $parts = [];

        if (isset($details['cycle_id']) && is_numeric($details['cycle_id'])) {
            $parts[] = 'цикл #'.(int) $details['cycle_id'];
        }

        if (isset($details['recipe_revision_id']) && is_numeric($details['recipe_revision_id'])) {
            $parts[] = 'ревизия #'.(int) $details['recipe_revision_id'];
        }

        if (isset($details['plant_id']) && is_numeric($details['plant_id'])) {
            $parts[] = 'растение #'.(int) $details['plant_id'];
        }

        $source = $this->toStringOrNull($details['source'] ?? null);
        if ($source !== null) {
            $parts[] = "источник {$source}";
        }

        if ($parts === []) {
            return 'Создан цикл';
        }

        return 'Создан цикл: '.implode(', ', $parts);
    }

    private function formatCycleStarted(array $details): string
    {
        $warnings = $details['warnings'] ?? null;
        if (is_array($warnings) && count($warnings) > 0) {
            return sprintf('Цикл запущен (предупреждений: %d)', count($warnings));
        }

        return 'Цикл запущен';
    }

    private function formatCyclePaused(array $details): string
    {
        $byUser = $this->toStringOrNull($details['user_name'] ?? null);
        if ($byUser !== null) {
            return "Цикл приостановлен пользователем {$byUser}";
        }

        return 'Цикл приостановлен';
    }

    private function formatCycleResumed(array $details): string
    {
        $byUser = $this->toStringOrNull($details['user_name'] ?? null);
        if ($byUser !== null) {
            return "Цикл возобновлён пользователем {$byUser}";
        }

        return 'Цикл возобновлён';
    }

    private function formatCycleHarvested(array $details): string
    {
        $batchLabel = $this->toStringOrNull($details['batch_label'] ?? null);
        if ($batchLabel !== null) {
            return "Цикл завершён: сбор урожая (партия {$batchLabel})";
        }

        return 'Цикл завершён: сбор урожая';
    }

    private function formatCycleAborted(array $details): string
    {
        $reason = $this->toStringOrNull($details['reason'] ?? null);
        if ($reason !== null) {
            return "Цикл аварийно остановлен: {$reason}";
        }

        return 'Цикл аварийно остановлен';
    }

    private function formatCycleAdjusted(array $details): string
    {
        if (isset($details['subsystems']) && is_array($details['subsystems'])) {
            $subsystemsSummary = $this->formatSubsystemsSummary($details['subsystems']);
            if ($subsystemsSummary !== null) {
                return 'Цикл скорректирован: '.$subsystemsSummary;
            }
        }

        $userName = $this->toStringOrNull($details['user_name'] ?? null);
        if ($userName !== null) {
            return "Цикл скорректирован пользователем {$userName}";
        }

        return 'Цикл скорректирован';
    }

    private function formatCyclePhaseAdvanced(array $details): string
    {
        $from = $this->formatPhaseIdentifier(
            $details['from_phase_id'] ?? null,
            $details['from_phase_template_id'] ?? null,
            $details['from_phase'] ?? null
        );
        $to = $this->formatPhaseIdentifier(
            $details['to_phase_id'] ?? null,
            $details['to_phase_template_id'] ?? null,
            $details['to_phase'] ?? null
        );

        if ($from !== null && $to !== null) {
            return "Переход фазы цикла: {$from} -> {$to}";
        }

        return 'Переход на следующую фазу цикла';
    }

    private function formatCyclePhaseSet(array $details): string
    {
        $to = $this->formatPhaseIdentifier(
            $details['to_phase_id'] ?? null,
            $details['to_phase_template_id'] ?? null,
            $details['to_phase'] ?? null
        );
        $comment = $this->toStringOrNull($details['comment'] ?? null);

        if ($to !== null && $comment !== null) {
            return "Фаза цикла вручную установлена: {$to} ({$comment})";
        }
        if ($to !== null) {
            return "Фаза цикла вручную установлена: {$to}";
        }

        return 'Фаза цикла вручную изменена';
    }

    private function formatCycleRecipeRevisionChanged(array $details): string
    {
        $from = is_numeric($details['from_revision_id'] ?? null) ? (int) $details['from_revision_id'] : null;
        $to = is_numeric($details['to_revision_id'] ?? null) ? (int) $details['to_revision_id'] : null;
        $applyMode = $this->toStringOrNull($details['apply_mode'] ?? null);
        $applyModeLabel = match ($applyMode) {
            'now' => 'немедленно',
            'next_phase' => 'со следующей фазы',
            default => null,
        };

        if ($from !== null && $to !== null && $applyModeLabel !== null) {
            return "Смена ревизии рецепта: #{$from} -> #{$to} ({$applyModeLabel})";
        }
        if ($from !== null && $to !== null) {
            return "Смена ревизии рецепта: #{$from} -> #{$to}";
        }

        return 'Смена ревизии рецепта';
    }

    private function formatCycleConfig(array $details): string
    {
        $mode = $this->toStringOrNull($details['mode'] ?? null);
        if ($mode === 'adjust') {
            return $this->formatCycleAdjusted($details);
        }
        if ($mode === 'start') {
            return 'Конфигурация цикла применена для запуска';
        }

        $subsystemsSummary = null;
        if (isset($details['subsystems']) && is_array($details['subsystems'])) {
            $subsystemsSummary = $this->formatSubsystemsSummary($details['subsystems']);
        }

        if ($subsystemsSummary !== null) {
            return 'Конфигурация цикла обновлена: '.$subsystemsSummary;
        }

        return 'Конфигурация цикла обновлена';
    }

    private function formatPhaseTransition(array $details): string
    {
        $from = $this->formatPhaseIdentifier($details['from_phase'] ?? null, null, null);
        $to = $this->formatPhaseIdentifier($details['to_phase'] ?? null, null, null);

        if ($from !== null && $to !== null) {
            return "Смена фазы: {$from} -> {$to}";
        }

        $phaseName = $this->toStringOrNull($details['phase_name'] ?? null);
        if ($phaseName !== null) {
            return "Смена фазы: {$phaseName}";
        }

        return 'Смена фазы';
    }

    private function formatZoneCommand(array $details): string
    {
        $command = $this->toStringOrNull($details['command_type'] ?? null) ?? 'UNKNOWN';

        $parts = [];

        $nodeUid = $this->toStringOrNull($details['node_uid'] ?? null);
        if ($nodeUid !== null) {
            $parts[] = "нода {$nodeUid}";
        }

        $channel = $this->toStringOrNull($details['channel'] ?? null);
        if ($channel !== null) {
            $parts[] = "канал {$channel}";
        }

        $userName = $this->toStringOrNull($details['user_name'] ?? null);
        if ($userName !== null) {
            $parts[] = "пользователь {$userName}";
        }

        if ($parts === []) {
            return "Команда зоны: {$command}";
        }

        return "Команда зоны: {$command} (".implode(', ', $parts).')';
    }

    private function formatWaterLevelLow(array $details): string
    {
        $context = $this->formatWaterLevelContext($details);
        if ($context !== null) {
            return "Низкий уровень воды ({$context})";
        }

        return 'Низкий уровень воды';
    }

    private function formatScheduleTaskFailed(array $details): string
    {
        $taskTypeRaw = $this->toStringOrNull($details['task_type'] ?? null);
        $taskType = $this->formatTaskTypeLabel($taskTypeRaw);
        $parts = [];

        $reasonRaw = $this->toStringOrNull($details['reason_code'] ?? null)
            ?? $this->toStringOrNull($details['reason'] ?? null);
        $reason = $this->formatKnownErrorCode($reasonRaw);
        if ($reason !== null) {
            $parts[] = "причина: {$reason}";
        }

        $statusRaw = $this->toStringOrNull($details['status'] ?? null);
        $status = $this->formatKnownStatus($statusRaw);
        if ($status !== null) {
            $parts[] = "статус: {$status}";
        }

        $errorCodeRaw = $this->toStringOrNull($details['error_code'] ?? null);
        $errorCode = $this->formatKnownErrorCode($errorCodeRaw);
        if ($errorCode !== null && $errorCodeRaw !== $reasonRaw) {
            $parts[] = "код ошибки: {$errorCode}";
        }

        $errorRaw = $this->toStringOrNull($details['error'] ?? null);
        $error = $this->formatKnownErrorCode($errorRaw);
        if ($error !== null && $errorRaw !== $reasonRaw) {
            $parts[] = "ошибка: {$error}";
        }

        $taskId = $this->toStringOrNull($details['task_id'] ?? null);
        if ($taskId !== null) {
            $parts[] = "ID задачи: {$taskId}";
        }

        $correlationId = $this->toStringOrNull($details['correlation_id'] ?? null);
        if ($correlationId !== null) {
            $parts[] = "корреляция: {$correlationId}";
        }

        if ($parts === []) {
            return "Scheduler: задача {$taskType} завершилась с ошибкой";
        }

        return "Scheduler: задача {$taskType} завершилась с ошибкой (".implode(', ', $parts).')';
    }

    private function formatSelfTaskDispatchRetryScheduled(array $details): string
    {
        $taskTypeRaw = $this->toStringOrNull($details['task_type'] ?? null);
        $taskType = $this->formatTaskTypeLabel($taskTypeRaw);
        $parts = [];

        $enqueueId = $this->toStringOrNull($details['enqueue_id'] ?? null);
        if ($enqueueId !== null) {
            $parts[] = "enqueue_id: {$enqueueId}";
        }

        $retryCount = isset($details['retry_count']) && is_numeric($details['retry_count'])
            ? (int) $details['retry_count']
            : null;
        $maxAttempts = isset($details['max_attempts']) && is_numeric($details['max_attempts'])
            ? (int) $details['max_attempts']
            : null;
        if ($retryCount !== null && $maxAttempts !== null) {
            $parts[] = "попытка {$retryCount}/{$maxAttempts}";
        } elseif ($retryCount !== null) {
            $parts[] = "попытка {$retryCount}";
        }

        $nextRetryAt = $this->toStringOrNull($details['next_retry_at'] ?? null);
        if ($nextRetryAt !== null) {
            $parts[] = "следующая попытка: {$nextRetryAt}";
        }

        if ($parts === []) {
            return "Scheduler запланировал повторную отправку для внутренней задачи {$taskType}";
        }

        return "Scheduler запланировал повторную отправку для внутренней задачи {$taskType} (".implode(', ', $parts).')';
    }

    private function formatPhCorrected(array $details): string
    {
        $current = $this->toFloatOrNull($details['current_ph'] ?? $details['current'] ?? null);
        $targetMin = $this->toFloatOrNull($details['target_ph_min'] ?? null);
        $targetMax = $this->toFloatOrNull($details['target_ph_max'] ?? null);
        $target = $this->toFloatOrNull($details['target_ph'] ?? $details['target'] ?? null);
        $durationMs = $this->toFloatOrNull($details['duration_ms'] ?? null);
        $dose = $this->toFloatOrNull($details['output'] ?? $details['ml'] ?? null);
        $direction = $this->toStringOrNull($details['direction'] ?? $details['correction_type'] ?? null);
        $channel = $this->toStringOrNull($details['channel'] ?? null);
        $attempt = isset($details['attempt']) ? (int) $details['attempt'] : null;

        $dirLabel = match ($direction) {
            'up' => 'вверх',
            'down' => 'вниз',
            default => $direction,
        };

        $parts = [];

        if ($current !== null) {
            $parts[] = sprintf('текущий pH %.2f', $current);
        }

        if ($targetMin !== null && $targetMax !== null) {
            $parts[] = sprintf('цель %.2f–%.2f', $targetMin, $targetMax);
        } elseif ($target !== null) {
            $parts[] = sprintf('цель %.2f', $target);
        }

        if ($durationMs !== null) {
            $parts[] = sprintf('импульс %d мс', (int) $durationMs);
        } elseif ($dose !== null) {
            $parts[] = sprintf('доза %.1f мл', $dose);
        }

        if ($channel !== null) {
            $parts[] = "канал {$channel}";
        }

        if ($attempt !== null && $attempt > 1) {
            $parts[] = "попытка {$attempt}";
        }

        $dirSuffix = $dirLabel !== null ? " ({$dirLabel})" : '';
        $detail = $parts !== [] ? ': '.implode(', ', $parts) : '';

        return "Коррекция pH{$dirSuffix}{$detail}";
    }

    private function formatEcDosing(array $details): string
    {
        $current = $this->toFloatOrNull($details['current_ec'] ?? $details['current'] ?? null);
        $targetMin = $this->toFloatOrNull($details['target_ec_min'] ?? null);
        $targetMax = $this->toFloatOrNull($details['target_ec_max'] ?? null);
        $target = $this->toFloatOrNull($details['target_ec'] ?? $details['target'] ?? null);
        $durationMs = $this->toFloatOrNull($details['duration_ms'] ?? null);
        $dose = $this->toFloatOrNull($details['output'] ?? $details['ml'] ?? null);
        $channel = $this->toStringOrNull($details['channel'] ?? null);
        $attempt = isset($details['attempt']) ? (int) $details['attempt'] : null;

        $parts = [];

        if ($current !== null) {
            $parts[] = sprintf('текущий EC %.2f мС/см', $current);
        }

        if ($targetMin !== null && $targetMax !== null) {
            $parts[] = sprintf('цель %.2f–%.2f мС/см', $targetMin, $targetMax);
        } elseif ($target !== null) {
            $parts[] = sprintf('цель %.2f мС/см', $target);
        }

        if ($durationMs !== null) {
            $parts[] = sprintf('импульс %d мс', (int) $durationMs);
        } elseif ($dose !== null) {
            $parts[] = sprintf('доза %.1f мл', $dose);
        }

        if ($channel !== null) {
            $parts[] = "канал {$channel}";
        }

        if ($attempt !== null && $attempt > 1) {
            $parts[] = "попытка {$attempt}";
        }

        $detail = $parts !== [] ? ': '.implode(', ', $parts) : '';

        return "Дозирование EC{$detail}";
    }

    private function formatPidOutput(array $details): string
    {
        $output = $this->toFloatOrNull($details['output'] ?? $details['ml'] ?? null);
        $error = $this->toFloatOrNull($details['error'] ?? $details['diff'] ?? null);
        $zoneState = $this->toStringOrNull($details['zone_state'] ?? $details['pid_zone'] ?? null);

        if ($output !== null && $error !== null) {
            $zonePart = $zoneState !== null ? " ({$zoneState})" : '';

            return sprintf('PID output: %.3f мл, ошибка %.4f%s', $output, $error, $zonePart);
        }

        return 'PID: расчёт выхода';
    }

    private function formatPidConfigUpdated(array $details): string
    {
        $pidType = $this->toStringOrNull($details['type'] ?? $details['pid_type'] ?? null);
        if ($pidType !== null) {
            return "Конфиг PID обновлён ({$pidType})";
        }

        return 'Конфиг PID обновлён';
    }

    private function formatProcessCalibrationSaved(array $details): string
    {
        $mode = $this->toStringOrNull($details['mode'] ?? null) ?? 'unknown';
        $window = $this->formatObserveWindow($details);
        $confidence = $this->toFloatOrNull($details['confidence'] ?? null);

        $parts = ["Process calibration обновлена ({$mode})"];
        if ($window !== null) {
            $parts[] = "окно {$window}";
        }
        if ($confidence !== null) {
            $parts[] = sprintf('confidence %.2f', $confidence);
        }

        $gains = [];
        foreach ([
            'ec_gain_per_ml' => 'EC',
            'ph_up_gain_per_ml' => 'pH+',
            'ph_down_gain_per_ml' => 'pH-',
        ] as $key => $label) {
            $value = $this->toFloatOrNull($details[$key] ?? null);
            if ($value !== null) {
                $gains[] = sprintf('%s=%.3f', $label, $value);
            }
        }
        if ($gains !== []) {
            $parts[] = implode(', ', $gains);
        }

        return implode(': ', array_filter([
            array_shift($parts),
            implode(', ', $parts),
        ]));
    }

    private function formatObserveWindow(array $details): ?string
    {
        $transport = $this->toFloatOrNull($details['transport_delay_sec'] ?? null);
        $settle = $this->toFloatOrNull($details['settle_sec'] ?? null);

        if ($transport === null && $settle === null) {
            return null;
        }

        $transportLabel = $transport !== null ? sprintf('%.0f', $transport) : '0';
        $settleLabel = $settle !== null ? sprintf('%.0f', $settle) : '0';

        return "{$transportLabel}+{$settleLabel} сек";
    }

    private function formatCorrectionStateTransition(array $details): string
    {
        $from = $this->toStringOrNull($details['from_state'] ?? null);
        $to = $this->toStringOrNull($details['to_state'] ?? null);
        $reason = $this->toStringOrNull($details['reason_code'] ?? null);

        if ($from !== null && $to !== null && $reason !== null) {
            return "Коррекция: {$from} -> {$to} ({$reason})";
        }
        if ($from !== null && $to !== null) {
            return "Коррекция: {$from} -> {$to}";
        }

        return 'Коррекция: переход состояния';
    }

    private function formatCorrectionComplete(array $details): string
    {
        $currentPh = $this->toFloatOrNull($details['current_ph'] ?? null);
        $currentEc = $this->toFloatOrNull($details['current_ec'] ?? null);
        $attempt = isset($details['attempt']) && is_numeric($details['attempt']) ? (int) $details['attempt'] : null;

        $parts = [];
        if ($currentPh !== null) {
            $parts[] = sprintf('pH %.2f', $currentPh);
        }
        if ($currentEc !== null) {
            $parts[] = sprintf('EC %.2f мС/см', $currentEc);
        }
        if ($attempt !== null && $attempt > 1) {
            $parts[] = "попытка {$attempt}";
        }

        return 'Коррекция завершена успешно'.($parts !== [] ? ' ('.implode(', ', $parts).')' : '');
    }

    private function formatCorrectionExhausted(array $details): string
    {
        $attempt = isset($details['attempt']) && is_numeric($details['attempt']) ? (int) $details['attempt'] : null;
        $maxAttempts = isset($details['max_attempts']) && is_numeric($details['max_attempts']) ? (int) $details['max_attempts'] : null;
        $stage = $this->toStringOrNull($details['stage'] ?? null);

        if ($attempt !== null && $maxAttempts !== null) {
            $message = "Коррекция: исчерпаны попытки ({$attempt}/{$maxAttempts})";

            return $stage !== null ? "{$message} [{$stage}]" : $message;
        }

        return $stage !== null ? "Коррекция: все попытки исчерпаны [{$stage}]" : 'Коррекция: все попытки исчерпаны';
    }

    private function formatCorrectionLimitPolicyApplied(array $details): string
    {
        $stageTimeoutSec = $this->toFloatOrNull($details['stage_timeout_sec'] ?? null);
        $parts = ['fill-stage без attempt caps'];
        if ($stageTimeoutSec !== null) {
            $parts[] = sprintf('таймаут %d с', (int) $stageTimeoutSec);
        }
        $parts[] = 'стоп только по no-effect/timeout';

        return 'Коррекция: применена политика лимитов'.' ('.implode(', ', $parts).')';
    }

    private function formatCorrectionAttemptCapIgnored(array $details): string
    {
        $capType = $this->toStringOrNull($details['cap_type'] ?? null) ?? 'unknown';
        $currentValue = isset($details['current_value']) && is_numeric($details['current_value']) ? (int) $details['current_value'] : null;
        $limitValue = isset($details['limit_value']) && is_numeric($details['limit_value']) ? (int) $details['limit_value'] : null;

        if ($currentValue !== null && $limitValue !== null) {
            return "Коррекция: лимит попыток {$capType} проигнорирован ({$currentValue}/{$limitValue}) в fill-stage";
        }

        return "Коррекция: лимит попыток {$capType} проигнорирован в fill-stage";
    }

    private function formatCorrectionSkippedDeadZone(array $details): string
    {
        $currentPh = $this->toFloatOrNull($details['current_ph'] ?? null);
        $currentEc = $this->toFloatOrNull($details['current_ec'] ?? null);
        $ecGap = $this->toFloatOrNull($details['ec_gap'] ?? null);
        $ecDeadband = $this->toFloatOrNull($details['ec_deadband'] ?? null);
        $phUpGap = $this->toFloatOrNull($details['ph_up_gap'] ?? null);
        $phDownGap = $this->toFloatOrNull($details['ph_down_gap'] ?? null);
        $phDeadband = $this->toFloatOrNull($details['ph_deadband'] ?? null);

        $parts = [];
        if ($currentPh !== null) {
            $parts[] = sprintf('pH %.2f', $currentPh);
        }
        if ($currentEc !== null) {
            $parts[] = sprintf('EC %.2f мС/см', $currentEc);
        }
        if ($ecGap !== null && $ecDeadband !== null) {
            $parts[] = sprintf('EC gap %.4f <= deadband %.4f', $ecGap, $ecDeadband);
        }
        if ($phUpGap !== null && $phDeadband !== null) {
            $parts[] = sprintf('pH+ gap %.4f <= deadband %.4f', $phUpGap, $phDeadband);
        }
        if ($phDownGap !== null && $phDeadband !== null) {
            $parts[] = sprintf('pH- gap %.4f <= deadband %.4f', $phDownGap, $phDeadband);
        }

        return 'Коррекция: мёртвая зона PID'.($parts !== [] ? ' ('.implode(', ', $parts).')' : '');
    }

    private function formatCorrectionSkippedCooldown(array $details): string
    {
        $retryAfterSec = $this->toFloatOrNull($details['retry_after_sec'] ?? null);
        $currentPh = $this->toFloatOrNull($details['current_ph'] ?? null);
        $currentEc = $this->toFloatOrNull($details['current_ec'] ?? null);

        $parts = [];
        if ($currentPh !== null) {
            $parts[] = sprintf('pH %.2f', $currentPh);
        }
        if ($currentEc !== null) {
            $parts[] = sprintf('EC %.2f мС/см', $currentEc);
        }
        if ($retryAfterSec !== null) {
            $parts[] = sprintf('повтор через %d с', (int) $retryAfterSec);
        }

        return 'Коррекция: кулдаун PID'.($parts !== [] ? ' ('.implode(', ', $parts).')' : '');
    }

    private function formatCorrectionSkippedDoseDiscarded(array $details): string
    {
        $reason = $this->toStringOrNull($details['reason'] ?? null);
        $durationMs = $this->toFloatOrNull($details['computed_duration_ms'] ?? null);
        $minDoseMs = $this->toFloatOrNull($details['min_dose_ms'] ?? null);
        $doseMl = $this->toFloatOrNull($details['dose_ml'] ?? null);
        $mlPerSec = $this->toFloatOrNull($details['ml_per_sec'] ?? null);

        $parts = [];
        if ($reason !== null) {
            $parts[] = $reason;
        }
        if ($durationMs !== null && $minDoseMs !== null) {
            $parts[] = sprintf('%dмс < %dмс', (int) $durationMs, (int) $minDoseMs);
        }
        if ($doseMl !== null) {
            $parts[] = sprintf('доза %.4f мл', $doseMl);
        }
        if ($mlPerSec !== null) {
            $parts[] = sprintf('насос %.4f мл/с', $mlPerSec);
        }

        return 'Коррекция: доза отброшена'.($parts !== [] ? ' ('.implode(', ', $parts).')' : '');
    }

    private function formatCorrectionSkippedWaterLevel(array $details): string
    {
        $waterLevelPct = $this->toFloatOrNull($details['water_level_pct'] ?? null);
        $retryAfterSec = $this->toFloatOrNull($details['retry_after_sec'] ?? null);

        $parts = [];
        if ($waterLevelPct !== null) {
            $parts[] = sprintf('уровень %.1f%%', $waterLevelPct);
        }
        if ($retryAfterSec !== null) {
            $parts[] = sprintf('повтор через %d с', (int) $retryAfterSec);
        }

        return 'Коррекция: мало воды'.($parts !== [] ? ' ('.implode(', ', $parts).')' : '');
    }

    private function formatCorrectionSkippedFreshness(array $details): string
    {
        $sensorScope = $this->toStringOrNull($details['sensor_scope'] ?? null);
        $sensorType = $this->toStringOrNull($details['sensor_type'] ?? null);
        $retryAfterSec = $this->toFloatOrNull($details['retry_after_sec'] ?? null);

        $parts = [];
        if ($sensorScope !== null) {
            $parts[] = $sensorScope === 'observe_window' ? 'observe window' : 'decision window';
        }
        if ($sensorType !== null) {
            $parts[] = strtoupper($sensorType);
        }
        if ($retryAfterSec !== null) {
            $parts[] = sprintf('повтор через %d с', (int) $retryAfterSec);
        }

        return 'Коррекция: устаревшие данные'.($parts !== [] ? ' ('.implode(', ', $parts).')' : '');
    }

    private function formatCorrectionSkippedWindowNotReady(array $details): string
    {
        $sensorScope = $this->toStringOrNull($details['sensor_scope'] ?? null);
        $sensorType = $this->toStringOrNull($details['sensor_type'] ?? null);
        $retryAfterSec = $this->toFloatOrNull($details['retry_after_sec'] ?? null);
        $reason = $this->toStringOrNull($details['reason'] ?? null);

        $parts = [];
        if ($sensorScope !== null) {
            $parts[] = $sensorScope === 'observe_window' ? 'observe window' : 'decision window';
        }
        if ($sensorType !== null) {
            $parts[] = strtoupper($sensorType);
        }
        if ($reason !== null) {
            $parts[] = $reason;
        }
        if ($retryAfterSec !== null) {
            $parts[] = sprintf('повтор через %d с', (int) $retryAfterSec);
        }

        return 'Коррекция: окно наблюдения не готово'.($parts !== [] ? ' ('.implode(', ', $parts).')' : '');
    }

    private function formatCorrectionObservationEvaluated(array $details): string
    {
        $pidType = $this->toStringOrNull($details['pid_type'] ?? null);
        $actualEffect = $this->toFloatOrNull($details['actual_effect'] ?? null);
        $expectedEffect = $this->toFloatOrNull($details['expected_effect'] ?? null);
        $thresholdEffect = $this->toFloatOrNull($details['threshold_effect'] ?? null);
        $noEffect = $details['is_no_effect'] ?? null;
        $nextCount = isset($details['no_effect_count_next']) && is_numeric($details['no_effect_count_next'])
            ? (int) $details['no_effect_count_next']
            : null;

        $parts = [];
        if ($pidType !== null) {
            $parts[] = strtoupper($pidType);
        }
        if ($actualEffect !== null && $expectedEffect !== null) {
            $parts[] = sprintf('эффект %.4f / ожидалось %.4f', $actualEffect, $expectedEffect);
        }
        if ($thresholdEffect !== null) {
            $parts[] = sprintf('порог %.4f', $thresholdEffect);
        }
        if (is_bool($noEffect)) {
            $parts[] = $noEffect ? 'no_effect=yes' : 'no_effect=no';
        }
        if ($nextCount !== null) {
            $parts[] = sprintf('счётчик %d', $nextCount);
        }

        return 'Коррекция: оценка отклика'.($parts !== [] ? ' ('.implode(', ', $parts).')' : '');
    }

    private function formatCorrectionNoEffect(array $details): string
    {
        $pidType = $this->toStringOrNull($details['pid_type'] ?? null);
        $actualEffect = $this->toFloatOrNull($details['actual_effect'] ?? null);
        $thresholdEffect = $this->toFloatOrNull($details['threshold_effect'] ?? null);
        $limit = isset($details['no_effect_limit']) && is_numeric($details['no_effect_limit']) ? (int) $details['no_effect_limit'] : null;

        $parts = [];
        if ($pidType !== null) {
            $parts[] = strtoupper($pidType);
        }
        if ($actualEffect !== null && $thresholdEffect !== null) {
            $parts[] = sprintf('эффект %.4f < %.4f', $actualEffect, $thresholdEffect);
        }
        if ($limit !== null) {
            $parts[] = sprintf('лимит %d', $limit);
        }

        return 'Коррекция: нет наблюдаемого эффекта'.($parts !== [] ? ' ('.implode(', ', $parts).')' : '');
    }

    private function formatRelayAutotuneComplete(array $details): string
    {
        $kp = $this->toFloatOrNull($details['kp'] ?? null);
        $ki = $this->toFloatOrNull($details['ki'] ?? null);
        $cycles = $details['cycles_detected'] ?? null;
        if ($kp !== null && $ki !== null && is_numeric($cycles)) {
            return sprintf('Автотюнинг завершён: Kp=%.3f, Ki=%.4f (%d циклов)', $kp, $ki, (int) $cycles);
        }

        return 'Relay-автотюнинг завершён';
    }

    private function formatPumpCalibrationSaved(array $details): string
    {
        $role = $this->toStringOrNull($details['role'] ?? null);
        $mlPerSec = $this->toFloatOrNull($details['ml_per_sec'] ?? null);

        if ($role !== null && $mlPerSec !== null) {
            return sprintf('Калибровка насоса [%s]: %.2f мл/с', $role, $mlPerSec);
        }

        return 'Калибровка насоса сохранена';
    }

    private function formatIrrStateSnapshot(array $details): string
    {
        $nodeUid = $this->toStringOrNull($details['node_uid'] ?? null);
        $snapshot = isset($details['snapshot']) && is_array($details['snapshot']) ? $details['snapshot'] : [];
        $pumpMain = array_key_exists('pump_main', $snapshot) ? ($snapshot['pump_main'] ? 'вкл' : 'выкл') : null;
        $cmdId = $this->toStringOrNull($details['cmd_id'] ?? null);

        $parts = [];
        if ($nodeUid !== null) {
            $parts[] = "нода {$nodeUid}";
        }
        if ($pumpMain !== null) {
            $parts[] = "насос {$pumpMain}";
        }
        if ($cmdId !== null) {
            $parts[] = "команда {$cmdId}";
        }

        return 'Снимок состояния ирригационного узла'.($parts !== [] ? ' ('.implode(', ', $parts).')' : '');
    }

    private function formatCommandTimeout(array $details): string
    {
        $cmdId = $this->toStringOrNull($details['cmd_id'] ?? null);
        $nodeUid = $this->toStringOrNull($details['node_uid'] ?? null);
        $channel = $this->toStringOrNull($details['channel'] ?? null);
        $timeoutMinutes = isset($details['timeout_minutes']) && is_numeric($details['timeout_minutes'])
            ? (int) $details['timeout_minutes']
            : null;
        $nodeStatus = $this->toStringOrNull($details['node_status'] ?? null);
        $nodeLastSeenAgeSec = isset($details['node_last_seen_age_sec']) && is_numeric($details['node_last_seen_age_sec'])
            ? (int) $details['node_last_seen_age_sec']
            : null;
        $staleCandidate = filter_var($details['node_stale_online_candidate'] ?? false, FILTER_VALIDATE_BOOL);

        $parts = [];
        if ($cmdId !== null) {
            $parts[] = "команда {$cmdId}";
        }
        if ($nodeUid !== null) {
            $parts[] = "нода {$nodeUid}";
        }
        if ($channel !== null) {
            $parts[] = "канал {$channel}";
        }
        if ($timeoutMinutes !== null) {
            $parts[] = "таймаут {$timeoutMinutes} мин";
        }
        if ($nodeStatus !== null) {
            $parts[] = "статус узла {$nodeStatus}";
        }
        if ($nodeLastSeenAgeSec !== null) {
            $parts[] = "last_seen {$nodeLastSeenAgeSec} с назад";
        }
        if ($staleCandidate) {
            $parts[] = 'узел числится online, но heartbeat устарел';
        }

        return 'Таймаут команды'.($parts !== [] ? ' ('.implode(', ', $parts).')' : '');
    }

    private function formatAeStartupProbeTimeout(array $details): string
    {
        $probeName = $this->toStringOrNull($details['probe_name'] ?? null) ?? 'irr_state_probe';
        $cmdId = $this->toStringOrNull($details['cmd_id'] ?? null);
        $nodeUid = $this->toStringOrNull($details['node_uid'] ?? null);
        $channel = $this->toStringOrNull($details['channel'] ?? null);
        $nodeStatus = $this->toStringOrNull($details['node_status'] ?? null);
        $nodeLastSeenAgeSec = isset($details['node_last_seen_age_sec']) && is_numeric($details['node_last_seen_age_sec'])
            ? (int) $details['node_last_seen_age_sec']
            : null;
        $staleCandidate = filter_var($details['node_stale_online_candidate'] ?? false, FILTER_VALIDATE_BOOL);

        $parts = ["probe {$probeName}"];
        if ($cmdId !== null) {
            $parts[] = "команда {$cmdId}";
        }
        if ($nodeUid !== null) {
            $parts[] = "нода {$nodeUid}";
        }
        if ($channel !== null) {
            $parts[] = "канал {$channel}";
        }
        if ($nodeStatus !== null) {
            $parts[] = "статус {$nodeStatus}";
        }
        if ($nodeLastSeenAgeSec !== null) {
            $parts[] = "last_seen {$nodeLastSeenAgeSec} с назад";
        }
        if ($staleCandidate) {
            $parts[] = 'online-статус выглядел устаревшим';
        }

        return 'Стартовый probe ирригационного контура не ответил'.($parts !== [] ? ' ('.implode(', ', $parts).')' : '');
    }

    private function formatPumpCalibrationFinished(array $details): string
    {
        $component = $this->toStringOrNull($details['component'] ?? null);
        $actualMl = $this->toFloatOrNull($details['actual_ml'] ?? null);
        $mlPerSec = $this->toFloatOrNull($details['ml_per_sec'] ?? null);

        if ($component !== null && $actualMl !== null && $mlPerSec !== null) {
            return sprintf('Калибровка насоса [%s]: %.2f мл, скорость %.2f мл/с', $component, $actualMl, $mlPerSec);
        }
        if ($component !== null) {
            return "Калибровка насоса [{$component}] завершена";
        }

        return 'Калибровка насоса завершена';
    }

    private function formatPumpCalibrationRunSkipped(array $details): string
    {
        $component = $this->toStringOrNull($details['component'] ?? null);
        $nodeUid = $this->toStringOrNull($details['node_uid'] ?? null);
        $reason = $this->toStringOrNull($details['reason'] ?? $details['reason_code'] ?? null);

        $parts = [];
        if ($nodeUid !== null) {
            $parts[] = "нода {$nodeUid}";
        }
        if ($reason !== null) {
            $parts[] = $reason;
        }

        if ($component !== null) {
            return 'Калибровка насоса ['.$component.'] пропущена'.($parts !== [] ? ' ('.implode(', ', $parts).')' : '');
        }

        return 'Калибровка насоса пропущена';
    }

    private function formatAeTaskStarted(array $details): string
    {
        $taskId = $this->toStringOrNull($details['task_id'] ?? null);
        $zoneId = $this->toStringOrNull($details['zone_id'] ?? null);

        if ($taskId !== null) {
            return "Задача автоматизации запущена (ID: {$taskId})";
        }
        if ($zoneId !== null) {
            return "Задача автоматизации запущена для зоны {$zoneId}";
        }

        return 'Задача автоматизации запущена';
    }

    private function formatAeTaskCompleted(array $details): string
    {
        $taskId = $this->toStringOrNull($details['task_id'] ?? null);
        if ($taskId !== null) {
            return "Задача автоматизации завершена (ID: {$taskId})";
        }

        return 'Задача автоматизации завершена';
    }

    private function formatAeTaskFailed(array $details): string
    {
        $errorCode = $this->toStringOrNull($details['error_code'] ?? null);
        $taskId = $this->toStringOrNull($details['task_id'] ?? null);

        $parts = [];
        if ($taskId !== null) {
            $parts[] = "ID: {$taskId}";
        }
        if ($errorCode !== null) {
            $parts[] = "ошибка: {$errorCode}";
        }

        return 'Ошибка задачи автоматизации'.($parts !== [] ? ' ('.implode(', ', $parts).')' : '');
    }

    private function formatSubsystemsSummary(array $subsystems): ?string
    {
        $parts = [];

        if (
            isset($subsystems['ph']['enabled'], $subsystems['ph']['targets'])
            && $subsystems['ph']['enabled'] === true
            && is_array($subsystems['ph']['targets'])
            && isset($subsystems['ph']['targets']['min'], $subsystems['ph']['targets']['max'])
        ) {
            $parts[] = sprintf(
                'pH %.1f–%.1f',
                (float) $subsystems['ph']['targets']['min'],
                (float) $subsystems['ph']['targets']['max']
            );
        }

        if (
            isset($subsystems['ec']['enabled'], $subsystems['ec']['targets'])
            && $subsystems['ec']['enabled'] === true
            && is_array($subsystems['ec']['targets'])
            && isset($subsystems['ec']['targets']['min'], $subsystems['ec']['targets']['max'])
        ) {
            $parts[] = sprintf(
                'EC %.1f–%.1f',
                (float) $subsystems['ec']['targets']['min'],
                (float) $subsystems['ec']['targets']['max']
            );
        }

        if (
            isset($subsystems['climate']['enabled'], $subsystems['climate']['targets'])
            && $subsystems['climate']['enabled'] === true
            && is_array($subsystems['climate']['targets'])
            && isset($subsystems['climate']['targets']['temperature'], $subsystems['climate']['targets']['humidity'])
        ) {
            $parts[] = sprintf(
                'Климат t=%.1f°C, RH=%.0f%%',
                (float) $subsystems['climate']['targets']['temperature'],
                (float) $subsystems['climate']['targets']['humidity']
            );
        }

        if (
            isset($subsystems['lighting']['enabled'], $subsystems['lighting']['targets'])
            && $subsystems['lighting']['enabled'] === true
            && is_array($subsystems['lighting']['targets'])
            && isset($subsystems['lighting']['targets']['hours_on'], $subsystems['lighting']['targets']['hours_off'])
        ) {
            $parts[] = sprintf(
                'Свет %.1fч / пауза %.1fч',
                (float) $subsystems['lighting']['targets']['hours_on'],
                (float) $subsystems['lighting']['targets']['hours_off']
            );
        }

        if (
            isset($subsystems['irrigation']['enabled'], $subsystems['irrigation']['targets'])
            && $subsystems['irrigation']['enabled'] === true
            && is_array($subsystems['irrigation']['targets'])
            && isset($subsystems['irrigation']['targets']['interval_minutes'], $subsystems['irrigation']['targets']['duration_seconds'])
        ) {
            $parts[] = sprintf(
                'Полив каждые %d мин, %d с',
                (int) $subsystems['irrigation']['targets']['interval_minutes'],
                (int) $subsystems['irrigation']['targets']['duration_seconds']
            );
        }

        return $parts !== [] ? implode('; ', $parts) : null;
    }

    private function formatPhaseIdentifier(mixed $primary, mixed $secondary, mixed $fallback): ?string
    {
        foreach ([$primary, $secondary, $fallback] as $value) {
            if (is_numeric($value)) {
                return '#'.(int) $value;
            }
            $string = $this->toStringOrNull($value);
            if ($string !== null) {
                return $string;
            }
        }

        return null;
    }

    private function toStringOrNull(mixed $value): ?string
    {
        if (is_string($value)) {
            $trimmed = trim($value);

            return $trimmed !== '' ? $trimmed : null;
        }

        if (is_numeric($value)) {
            return (string) $value;
        }

        return null;
    }

    private function toFloatOrNull(mixed $value): ?float
    {
        if (! is_numeric($value)) {
            return null;
        }

        return (float) $value;
    }

    private function formatWaterLevelContext(array $details): ?string
    {
        $level = $this->normalizeWaterLevelValue($details['level'] ?? null);
        $threshold = $this->normalizeWaterLevelValue($details['threshold'] ?? null);

        if ($level === null && $threshold === null) {
            return null;
        }

        $parts = [];
        if ($level !== null) {
            $parts[] = "уровень {$level}";
        }
        if ($threshold !== null) {
            $parts[] = "порог {$threshold}";
        }

        return implode(', ', $parts);
    }

    private function normalizeWaterLevelValue(mixed $value): ?string
    {
        if (! is_numeric($value)) {
            return null;
        }

        $numeric = (float) $value;
        if ($numeric <= 1.0) {
            $numeric *= 100.0;
        }

        return sprintf('%.1f%%', $numeric);
    }

    private function formatKnownErrorCode(?string $code): ?string
    {
        if ($code === null) {
            return null;
        }

        return match ($code) {
            'submit_failed' => 'не удалось отправить задачу',
            'task_due_deadline_exceeded' => 'превышен дедлайн выполнения задачи',
            'zone_not_found' => 'зона не найдена',
            default => $code,
        };
    }

    private function formatKnownStatus(?string $status): ?string
    {
        if ($status === null) {
            return null;
        }

        return match ($status) {
            'rejected' => 'отклонена',
            'failed' => 'ошибка',
            'expired' => 'просрочена',
            'completed' => 'выполнена',
            'accepted' => 'принята',
            'running' => 'выполняется',
            default => $status,
        };
    }

    private function formatTaskTypeLabel(?string $taskType): string
    {
        if ($taskType === null) {
            return 'неизвестного типа';
        }

        return match ($taskType) {
            'diagnostics' => 'диагностики',
            'lighting' => 'освещения',
            'ventilation' => 'вентиляции',
            'irrigation' => 'полива',
            'solution_change' => 'смены раствора',
            'mist' => 'тумана',
            default => $taskType,
        };
    }

    private function formatAlertTriggered(array $details): string
    {
        $alertType = $this->toStringOrNull($details['alert_type'] ?? $details['type'] ?? null);
        $message = $this->toStringOrNull($details['message'] ?? null);

        if ($message !== null) {
            return "Тревога: {$message}";
        }
        if ($alertType !== null) {
            return "Тревога сработала: {$alertType}";
        }

        return 'Тревога сработала';
    }

    private function formatNodeEvent(array $details, string $verb): string
    {
        $nodeUid = $this->toStringOrNull($details['node_uid'] ?? $details['node_id'] ?? null);
        if ($nodeUid !== null) {
            return "Узел {$nodeUid} {$verb}";
        }

        return "Узел {$verb}";
    }

    private function formatManualIntervention(array $details): string
    {
        $user = $this->toStringOrNull($details['user'] ?? $details['user_id'] ?? null);
        $action = $this->toStringOrNull($details['action'] ?? null);

        if ($user !== null && $action !== null) {
            return "Ручное вмешательство: {$action} (пользователь {$user})";
        }
        if ($action !== null) {
            return "Ручное вмешательство: {$action}";
        }
        if ($user !== null) {
            return "Ручное вмешательство (пользователь {$user})";
        }

        return 'Ручное вмешательство';
    }

    private function formatCalibrationEvent(array $details, string $base): string
    {
        $component = $this->toStringOrNull($details['component'] ?? null);
        if ($component !== null) {
            return "{$base} [{$component}]";
        }

        return $base;
    }

    private function formatRecipeEvent(array $details, string $base): string
    {
        $recipeName = $this->toStringOrNull($details['recipe_name'] ?? null);
        $recipeId = $this->toStringOrNull($details['recipe_id'] ?? null);

        if ($recipeName !== null) {
            return "{$base}: {$recipeName}";
        }
        if ($recipeId !== null) {
            return "{$base} (ID: {$recipeId})";
        }

        return $base;
    }

    private function formatPhaseChange(array $details): string
    {
        $from = $this->toStringOrNull($details['from_phase'] ?? $details['from'] ?? null);
        $to = $this->toStringOrNull($details['to_phase'] ?? $details['to'] ?? null);

        if ($from !== null && $to !== null) {
            return "Смена фазы: {$from} → {$to}";
        }
        if ($to !== null) {
            return "Смена фазы: {$to}";
        }

        return 'Смена фазы';
    }
}
