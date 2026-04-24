<?php

declare(strict_types=1);

namespace App\Services\Scheduler;

use App\Models\AeTask;
use App\Models\Command;
use App\Models\ZoneEvent;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\Schema;

/**
 * Собирает причинно-следственную цепочку для UI Cockpit по заданному
 * `execution_id` (= `ae_tasks.id`).
 *
 * Шаги цепочки (в порядке):
 *   1. SNAPSHOT   — из `ae_tasks.corr_snapshot_event_id` → `zone_events`
 *   2. DECISION   — агрегат `irrigation_decision_*` / `corr_*` из `ae_tasks`
 *   3. TASK       — сама запись `ae_tasks` (принята в очередь)
 *   4. DISPATCH   — первая команда, отправленная в `history-logger` (`commands`)
 *   5. RUNNING    — момент получения ACK / начала исполнения узлом
 *   6. COMPLETE / FAIL / SKIP — терминальный статус `ae_tasks.status`
 *
 * SKIP-run может содержать только SNAPSHOT + DECISION без DISPATCH/RUNNING —
 * это нормально.
 *
 * @see doc_ai/04_BACKEND_CORE/ae3lite.md
 * @see doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md
 */
class ExecutionChainAssembler
{
    /**
     * @return array<int, array{step: string, at: ?string, ref: string, detail: string, status: string, live?: bool}>
     */
    public function assemble(int $zoneId, string $executionId): array
    {
        $normalizedId = trim($executionId);
        if ($normalizedId === '' || preg_match('/^\d+$/', $normalizedId) !== 1) {
            return [];
        }

        if (! Schema::hasTable('ae_tasks')) {
            return [];
        }

        $task = AeTask::query()
            ->where('zone_id', $zoneId)
            ->where('id', (int) $normalizedId)
            ->first();

        if ($task === null) {
            return [];
        }

        $chain = [];

        $snapshotStep = $this->snapshotStep($task);
        if ($snapshotStep !== null) {
            $chain[] = $snapshotStep;
        }

        $decisionStep = $this->decisionStep($task);
        if ($decisionStep !== null) {
            $chain[] = $decisionStep;
        }

        $chain[] = $this->taskStep($task);

        $dispatch = $this->dispatchStep($task);
        if ($dispatch !== null) {
            $chain[] = $dispatch;
        }

        $running = $this->runningStep($task);
        if ($running !== null) {
            $chain[] = $running;
        }

        $terminal = $this->terminalStep($task);
        if ($terminal !== null) {
            $chain[] = $terminal;
        }

        return $chain;
    }

    /**
     * @return array{step: string, at: ?string, ref: string, detail: string, status: string}|null
     */
    private function snapshotStep(AeTask $task): ?array
    {
        $eventId = $task->corr_snapshot_event_id;
        if ($eventId === null) {
            return null;
        }

        $event = ZoneEvent::query()->where('id', $eventId)->first();
        if ($event === null) {
            return [
                'step' => 'SNAPSHOT',
                'at' => $this->toIso($task->corr_snapshot_created_at),
                'ref' => (string) $eventId,
                'detail' => 'Снимок входных данных (событие недоступно)',
                'status' => 'ok',
            ];
        }

        return [
            'step' => 'SNAPSHOT',
            'at' => $this->toIso($event->created_at ?? $task->corr_snapshot_created_at),
            'ref' => (string) $event->id,
            'detail' => $this->describeSnapshot($event, $task),
            'status' => 'ok',
        ];
    }

    /**
     * @return array{step: string, at: ?string, ref: string, detail: string, status: string}|null
     */
    private function decisionStep(AeTask $task): ?array
    {
        $outcome = $task->irrigation_decision_outcome ?? null;
        $strategy = $task->irrigation_decision_strategy ?? null;
        $reasonCode = $task->irrigation_decision_reason_code ?? null;
        $bundle = $task->irrigation_bundle_revision ?? null;
        $corrStep = $task->corr_step ?? null;

        if ($outcome === null && $strategy === null && $reasonCode === null && $corrStep === null) {
            return null;
        }

        $detail = $this->describeDecision($task);
        $status = match (strtolower((string) $outcome)) {
            'fail' => 'err',
            'skip' => 'skip',
            default => $task->irrigation_decision_degraded ? 'warn' : 'ok',
        };

        return [
            'step' => 'DECISION',
            'at' => $this->toIso($task->created_at),
            'ref' => $this->decisionRef($task),
            'detail' => $detail,
            'status' => $status,
        ];
    }

    /**
     * @return array{step: string, at: ?string, ref: string, detail: string, status: string}
     */
    private function taskStep(AeTask $task): array
    {
        $intentKey = $task->intent?->idempotency_key;
        $detail = sprintf(
            'ae_task #%d · %s · стадия %s',
            (int) $task->id,
            $task->task_type,
            $task->current_stage,
        );
        if ($intentKey !== null && $intentKey !== '') {
            $detail .= " · intent {$intentKey}";
        }

        return [
            'step' => 'TASK',
            'at' => $this->toIso($task->created_at),
            'ref' => 'T-'.$task->id,
            'detail' => $detail,
            'status' => 'ok',
        ];
    }

    /**
     * @return array{step: string, at: ?string, ref: string, detail: string, status: string}|null
     */
    private function dispatchStep(AeTask $task): ?array
    {
        $command = $this->firstCommandForTask($task);
        if ($command === null) {
            return null;
        }

        $rawStatus = strtoupper((string) $command->status);
        $status = match (true) {
            in_array($rawStatus, ['ERROR', 'INVALID', 'TIMEOUT', 'SEND_FAILED'], true) => 'err',
            default => 'ok',
        };

        $node = $command->node_id !== null ? "node#{$command->node_id}" : 'node=—';
        $detail = sprintf(
            'history-logger → %s %s · %s',
            $node,
            (string) $command->channel,
            (string) $command->cmd,
        );

        return [
            'step' => 'DISPATCH',
            'at' => $this->toIso($command->sent_at ?? $command->created_at),
            'ref' => 'cmd-'.$command->id,
            'detail' => $detail,
            'status' => $status,
        ];
    }

    /**
     * @return array{step: string, at: ?string, ref: string, detail: string, status: string, live?: bool}|null
     */
    private function runningStep(AeTask $task): ?array
    {
        $statuses = ['running', 'claimed', 'waiting_command'];
        $isActive = in_array((string) $task->status, $statuses, true);
        $command = $this->firstCommandForTask($task);

        // SKIP-решение никогда не выходило в исполнение — RUNNING-шаг не нужен.
        $decisionOutcome = strtolower((string) ($task->irrigation_decision_outcome ?? ''));
        if (! $isActive && $decisionOutcome === 'skip') {
            return null;
        }

        // Для pending-задачи без ACK команд тоже не показываем RUNNING — она
        // ещё не стартовала.
        if (! $isActive && $command?->ack_at === null && $task->status === 'pending') {
            return null;
        }

        // Cancelled задача, которая не успела запуститься, тоже без RUNNING.
        if (! $isActive && $task->status === 'cancelled' && $task->claimed_at === null) {
            return null;
        }

        $ranAt = $command?->ack_at ?? $task->claimed_at;
        if ($ranAt === null && ! $isActive) {
            return null;
        }
        $ranAt ??= $task->updated_at;

        if ($ranAt === null) {
            return null;
        }

        $detail = $isActive
            ? "Активно: {$task->current_stage}"
            : 'Запуск исполнения на узле';

        return [
            'step' => 'RUNNING',
            'at' => $this->toIso($ranAt),
            'ref' => 'ex-'.$task->id,
            'detail' => $detail,
            'status' => 'run',
            'live' => $isActive,
        ];
    }

    /**
     * @return array{step: string, at: ?string, ref: string, detail: string, status: string}|null
     */
    private function terminalStep(AeTask $task): ?array
    {
        $status = strtolower((string) $task->status);
        if (! in_array($status, ['completed', 'failed', 'cancelled'], true)) {
            return null;
        }

        if ($status === 'completed') {
            $outcome = strtolower((string) ($task->irrigation_decision_outcome ?? ''));
            if ($outcome === 'skip') {
                return [
                    'step' => 'SKIP',
                    'at' => $this->toIso($task->completed_at ?? $task->updated_at),
                    'ref' => 'ex-'.$task->id,
                    'detail' => $this->describeSkip($task),
                    'status' => 'skip',
                ];
            }

            return [
                'step' => 'COMPLETE',
                'at' => $this->toIso($task->completed_at ?? $task->updated_at),
                'ref' => 'ex-'.$task->id,
                'detail' => 'Задача завершена успешно',
                'status' => 'ok',
            ];
        }

        $errorCode = (string) ($task->error_code ?? 'UNKNOWN');
        $errorMessage = (string) ($task->error_message ?? '');
        $detail = trim($errorCode.' · '.$errorMessage, ' ·') ?: 'Задача завершилась с ошибкой';

        return [
            'step' => 'FAIL',
            'at' => $this->toIso($task->completed_at ?? $task->updated_at),
            'ref' => 'ex-'.$task->id,
            'detail' => $detail,
            'status' => 'err',
        ];
    }

    private function firstCommandForTask(AeTask $task): ?Command
    {
        $intentKey = $task->intent?->idempotency_key;
        $cmdId = $task->corr_snapshot_cmd_id;

        $query = Command::query()
            ->where('zone_id', $task->zone_id);

        if (is_string($cmdId) && $cmdId !== '') {
            return $query->where('cmd_id', $cmdId)->orderBy('created_at')->first() ?? null;
        }

        if (is_string($intentKey) && $intentKey !== '') {
            $command = $query->where('request_id', $intentKey)
                ->orderBy('created_at')
                ->first();
            if ($command !== null) {
                return $command;
            }
        }

        // Fallback: ближайшая по времени команда в окне создания таски.
        $from = $task->created_at?->copy()->subSeconds(5);
        $to = ($task->completed_at ?? $task->updated_at ?? $task->created_at)?->copy()->addSeconds(5);
        if ($from === null || $to === null) {
            return null;
        }

        return $query
            ->whereBetween('created_at', [$from, $to])
            ->orderBy('created_at')
            ->first();
    }

    private function describeSnapshot(ZoneEvent $event, AeTask $task): string
    {
        $payload = is_array($event->payload_json) ? $event->payload_json : [];
        $parts = [];

        foreach (['ph', 'ec', 'tank_temp_c'] as $field) {
            if (isset($payload[$field]) && is_numeric($payload[$field])) {
                $parts[] = sprintf('%s=%s', strtoupper($field), (string) $payload[$field]);
            }
        }

        if ($parts === []) {
            $type = (string) ($task->corr_snapshot_source_event_type ?? $event->type ?? 'snapshot');

            return "Снимок {$type}";
        }

        return implode(' · ', $parts);
    }

    private function describeDecision(AeTask $task): string
    {
        $parts = [];
        $outcome = strtoupper((string) ($task->irrigation_decision_outcome ?? ''));
        if ($outcome !== '') {
            $parts[] = $outcome;
        }
        if ($task->irrigation_decision_strategy !== null) {
            $parts[] = 'strategy='.$task->irrigation_decision_strategy;
        }
        if ($task->corr_step !== null) {
            $parts[] = 'corr_step='.$task->corr_step;
        }
        if ($task->irrigation_bundle_revision !== null) {
            $parts[] = 'bundle '.$task->irrigation_bundle_revision;
        }
        if ($task->irrigation_decision_reason_code !== null) {
            $parts[] = $task->irrigation_decision_reason_code;
        }

        return $parts === [] ? 'Решение AE3' : implode(' · ', $parts);
    }

    private function describeSkip(AeTask $task): string
    {
        $reason = (string) ($task->irrigation_decision_reason_code ?? 'skip');

        return "Пропуск · {$reason}";
    }

    private function decisionRef(AeTask $task): string
    {
        $eventId = $task->corr_snapshot_event_id;
        if ($eventId !== null) {
            return 'cw-'.$eventId;
        }

        return 'cw-t'.$task->id;
    }

    private function toIso(mixed $value): ?string
    {
        if ($value === null || $value === '') {
            return null;
        }

        try {
            if ($value instanceof \DateTimeInterface) {
                return CarbonImmutable::instance($value)->utc()->toIso8601String();
            }

            return CarbonImmutable::parse((string) $value)->utc()->toIso8601String();
        } catch (\Throwable) {
            return null;
        }
    }
}
