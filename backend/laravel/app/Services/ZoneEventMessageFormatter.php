<?php

namespace App\Services;

class ZoneEventMessageFormatter
{
    /**
     * Сформировать человекочитаемое сообщение события зоны.
     */
    public function format(?string $type, mixed $details): string
    {
        $eventType = strtoupper((string) ($type ?? ''));
        $payload = $this->normalizeDetails($details);

        $explicitMessage = $this->extractExplicitMessage($payload);
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

    private function extractExplicitMessage(array $details): ?string
    {
        $direct = $this->toStringOrNull($details['message'] ?? null)
            ?? $this->toStringOrNull($details['msg'] ?? null);

        if ($direct !== null) {
            return $direct;
        }

        if (isset($details['details']) && is_array($details['details'])) {
            $nested = $this->toStringOrNull($details['details']['message'] ?? null)
                ?? $this->toStringOrNull($details['details']['msg'] ?? null);

            if ($nested !== null) {
                return $nested;
            }
        }

        return null;
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
}
