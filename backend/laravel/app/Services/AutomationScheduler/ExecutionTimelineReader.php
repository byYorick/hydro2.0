<?php

namespace App\Services\AutomationScheduler;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class ExecutionTimelineReader
{
    /**
     * @return array<int, array<string, mixed>>
     */
    public function readForExecution(int $zoneId, string $taskId, ?string $correlationId, int $limit = 200): array
    {
        $normalizedTaskId = trim($taskId);
        $normalizedCorrelationId = trim((string) $correlationId);
        if ($normalizedTaskId === '' && $normalizedCorrelationId === '') {
            return [];
        }

        if (! Schema::hasTable('zone_events')) {
            return [];
        }

        $payloadColumn = $this->payloadColumn();
        $safeLimit = max(1, min($limit, 500));

        $rows = DB::table('zone_events')
            ->where('zone_id', $zoneId)
            ->where(function ($query) use ($payloadColumn, $normalizedTaskId, $normalizedCorrelationId): void {
                if ($normalizedTaskId !== '') {
                    $query->whereRaw("{$payloadColumn}->>'task_id' = ?", [$normalizedTaskId]);
                }

                if ($normalizedCorrelationId !== '') {
                    $method = $normalizedTaskId !== '' ? 'orWhereRaw' : 'whereRaw';
                    $query->{$method}("{$payloadColumn}->>'correlation_id' = ?", [$normalizedCorrelationId]);
                }
            })
            ->orderBy('created_at')
            ->orderBy('id')
            ->limit($safeLimit)
            ->get([
                'id',
                'type',
                DB::raw("{$payloadColumn} as details"),
                'created_at',
            ]);

        return $rows->map(function ($row) use ($normalizedTaskId, $normalizedCorrelationId): array {
            $details = $this->normalizeDetails($row->details ?? null);
            $result = is_array($details['result'] ?? null) ? $details['result'] : [];

            $eventType = is_string($details['event_type'] ?? null) && trim((string) $details['event_type']) !== ''
                ? trim((string) $details['event_type'])
                : (string) ($row->type ?? 'unknown');

            return [
                'event_id' => (string) ($details['event_id'] ?? $details['ws_event_id'] ?? $row->id),
                'event_seq' => isset($details['event_seq']) && is_numeric($details['event_seq']) ? (int) $details['event_seq'] : null,
                'event_type' => $eventType,
                'type' => (string) ($row->type ?? $eventType),
                'at' => $this->toIso8601($row->created_at ?? null),
                'task_id' => is_string($details['task_id'] ?? null) ? (string) $details['task_id'] : ($normalizedTaskId !== '' ? $normalizedTaskId : null),
                'correlation_id' => is_string($details['correlation_id'] ?? null) ? (string) $details['correlation_id'] : ($normalizedCorrelationId !== '' ? $normalizedCorrelationId : null),
                'task_type' => is_string($details['task_type'] ?? null) ? (string) $details['task_type'] : null,
                'stage' => $this->resolveString($details['stage'] ?? $details['current_stage'] ?? null),
                'status' => is_string($details['status'] ?? null) ? (string) $details['status'] : null,
                'terminal_status' => is_string($details['terminal_status'] ?? null) ? (string) $details['terminal_status'] : null,
                'decision' => $this->resolveString($details['decision'] ?? $result['decision'] ?? null),
                'reason_code' => $this->resolveString($details['reason_code'] ?? $result['reason_code'] ?? null),
                'reason' => $this->resolveString($details['reason'] ?? $result['reason'] ?? null),
                'error_code' => $this->resolveString($details['error_code'] ?? $result['error_code'] ?? null),
                'node_uid' => $this->resolveString($details['node_uid'] ?? null),
                'channel' => $this->resolveString($details['channel'] ?? null),
                'cmd' => $this->resolveString($details['cmd'] ?? null),
                'command_submitted' => $this->normalizeOptionalBool($details['command_submitted'] ?? $result['command_submitted'] ?? null),
                'command_effect_confirmed' => $this->normalizeOptionalBool($details['command_effect_confirmed'] ?? $result['command_effect_confirmed'] ?? null),
                'details' => $details,
                'source' => 'zone_events',
            ];
        })->values()->all();
    }

    private function payloadColumn(): string
    {
        return Schema::hasColumn('zone_events', 'payload_json') ? 'payload_json' : 'details';
    }

    /**
     * @return array<string, mixed>
     */
    private function normalizeDetails(mixed $value): array
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

    private function toIso8601(mixed $value): ?string
    {
        if ($value === null || $value === '') {
            return null;
        }

        try {
            return \Carbon\CarbonImmutable::parse((string) $value)->utc()->toIso8601String();
        } catch (\Throwable) {
            return null;
        }
    }

    private function normalizeOptionalBool(mixed $value): ?bool
    {
        if (is_bool($value)) {
            return $value;
        }
        if (is_int($value) || is_float($value)) {
            return (bool) $value;
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

    private function resolveString(mixed $value): ?string
    {
        if (! is_string($value)) {
            return null;
        }

        $normalized = trim($value);

        return $normalized !== '' ? $normalized : null;
    }
}
