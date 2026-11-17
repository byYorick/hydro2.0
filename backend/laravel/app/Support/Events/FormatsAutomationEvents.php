<?php

namespace App\Support\Events;

/** Automation event wording composed with the shared zone-event scalar formatters. */
trait FormatsAutomationEvents
{
    private function formatIrrigationDecisionSnapshotLocked(array $details): string
    {
        $strategy = $this->irrigationStrategyLabel($this->toStringOrNull($details['strategy'] ?? null) ?? 'task');
        $bundleRevision = $this->toStringOrNull($details['bundle_revision'] ?? null);
        if ($bundleRevision !== null) {
            return sprintf(
                'Настройки полива зафиксированы: %s (%s)',
                $strategy,
                substr($bundleRevision, 0, 12)
            );
        }

        return sprintf('Настройки полива зафиксированы: %s', $strategy);
    }

    private function formatIrrigationDecisionEvaluated(array $details): string
    {
        $outcome = strtolower($this->toStringOrNull($details['outcome'] ?? null) ?? '');
        $strategy = $this->toStringOrNull($details['strategy'] ?? null);
        $degraded = filter_var($details['degraded'] ?? false, FILTER_VALIDATE_BOOL);

        $base = match ($outcome) {
            'skip' => 'Полив пропущен',
            'degraded_run' => 'Полив разрешён с пониженной достоверностью данных',
            'fail' => 'Полив не разрешён: ошибка проверки условий',
            'run' => 'Полив разрешён',
            default => 'Результат решения о поливе неизвестен',
        };

        $parts = [];
        if ($strategy !== null) {
            $parts[] = $this->irrigationStrategyLabel($strategy);
        }
        if ($degraded && $outcome !== 'degraded_run') {
            $parts[] = 'пониженная достоверность данных';
        }

        return $parts !== []
            ? sprintf('%s (%s)', $base, implode(', ', $parts))
            : $base;
    }

    private function irrigationStrategyLabel(string $strategy): string
    {
        return match ($strategy) {
            'task', 'schedule' => 'по расписанию',
            'smart_soil_v1' => 'по влажности субстрата',
            default => 'неизвестное условие полива',
        };
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
}
