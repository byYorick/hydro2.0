<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\SchedulerLog;
use App\Models\Zone;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\Response;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Schema;

class SchedulerTaskController extends Controller
{
    private const TASK_TIMELINE_EVENT_TYPES = [
        'TASK_RECEIVED',
        'TASK_STARTED',
        'DECISION_MADE',
        'COMMAND_DISPATCHED',
        'COMMAND_FAILED',
        'TASK_FINISHED',
        'SCHEDULE_TASK_ACCEPTED',
        'SCHEDULE_TASK_COMPLETED',
        'SCHEDULE_TASK_FAILED',
        'SCHEDULE_TASK_EXECUTION_STARTED',
        'SCHEDULE_TASK_EXECUTION_FINISHED',
        'SCHEDULE_TASK_FALLBACK_EVENT_ONLY',
        'SCHEDULE_DIAGNOSTICS_REQUESTED',
        'SELF_TASK_ENQUEUED',
        'SELF_TASK_DISPATCHED',
        'SELF_TASK_DISPATCH_FAILED',
        'SELF_TASK_EXPIRED',
        'CYCLE_START_INITIATED',
        'NODES_AVAILABILITY_CHECKED',
        'TANK_LEVEL_CHECKED',
        'TANK_REFILL_STARTED',
        'TANK_REFILL_COMPLETED',
        'TANK_REFILL_TIMEOUT',
    ];

    public function index(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $limit = (int) $request->integer('limit', 20);
        $limit = max(1, min($limit, 100));
        $includeTimeline = $request->boolean('include_timeline', false);

        $rows = SchedulerLog::query()
            ->where('task_name', 'like', 'ae_scheduler_task_st-%')
            ->whereRaw("jsonb_exists(details, 'zone_id') AND (details->>'zone_id') ~ '^[0-9]+$' AND (details->>'zone_id')::int = ?", [$zone->id])
            ->orderByDesc('created_at')
            ->orderByDesc('id')
            ->limit(max(200, $limit * 10))
            ->get(['id', 'task_name', 'status', 'details', 'created_at']);

        $tasks = $this->aggregateTaskRows($rows, $limit, $zone->id, $includeTimeline);

        return response()->json([
            'status' => 'ok',
            'data' => $tasks,
        ]);
    }

    public function show(Request $request, Zone $zone, string $taskId): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        if (! preg_match('/^st-[A-Za-z0-9\-_.:]{6,128}$/', $taskId)) {
            return response()->json([
                'status' => 'error',
                'code' => 'VALIDATION_ERROR',
                'message' => 'Некорректный task_id',
            ], 422);
        }

        $automationTask = null;
        $automationError = null;

        try {
            $automationTask = $this->fetchTaskFromAutomationEngine($taskId);
        } catch (\Throwable $e) {
            $automationError = $e;
            Log::warning('SchedulerTaskController: automation-engine task status unavailable', [
                'task_id' => $taskId,
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);
        }

        if (is_array($automationTask)) {
            $taskZoneId = (int) ($automationTask['zone_id'] ?? 0);
            if ($taskZoneId !== (int) $zone->id) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'NOT_FOUND',
                    'message' => 'Task not found for this zone',
                ], 404);
            }

            $lifecycle = $this->buildLifecycle($taskId, $zone->id);
            $payload = $this->normalizeTaskPayload($automationTask, $taskId, 'automation_engine');
            $payload['lifecycle'] = $lifecycle;
            $payload['timeline'] = $this->buildTaskTimeline(
                $zone->id,
                (string) ($payload['task_id'] ?? $taskId),
                is_string($payload['correlation_id'] ?? null) ? $payload['correlation_id'] : null
            );

            return response()->json([
                'status' => 'ok',
                'data' => $payload,
            ]);
        }

        $dbTask = $this->loadTaskFromSchedulerLogs($taskId, $zone->id);
        if ($dbTask !== null) {
            return response()->json([
                'status' => 'ok',
                'data' => $dbTask,
            ]);
        }

        if ($automationError instanceof ConnectionException || $automationError instanceof RequestException) {
            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_UNAVAILABLE',
                'message' => 'Automation-engine недоступен, и локальный снимок задачи не найден.',
            ], 503);
        }

        return response()->json([
            'status' => 'error',
            'code' => 'NOT_FOUND',
            'message' => 'Task not found',
        ], 404);
    }

    private function authorizeZoneAccess(Request $request, Zone $zone): void
    {
        $user = $request->user();
        if (! $user) {
            abort(401, 'Unauthorized');
        }

        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            abort(403, 'Forbidden: Access denied to this zone');
        }
    }

    private function fetchTaskFromAutomationEngine(string $taskId): ?array
    {
        $apiUrl = rtrim((string) config('services.automation_engine.api_url', 'http://automation-engine:9405'), '/');
        $timeout = (float) config('services.automation_engine.timeout', 2.0);

        /** @var Response $response */
        $response = Http::acceptJson()->timeout($timeout)->get("{$apiUrl}/scheduler/task/{$taskId}");

        if ($response->status() === 404) {
            return null;
        }

        $response->throw();

        $payload = $response->json();
        if (! is_array($payload) || ($payload['status'] ?? null) !== 'ok') {
            return null;
        }

        $data = $payload['data'] ?? null;

        return is_array($data) ? $data : null;
    }

    private function loadTaskFromSchedulerLogs(string $taskId, int $zoneId): ?array
    {
        $rows = SchedulerLog::query()
            ->where('task_name', 'ae_scheduler_task_'.$taskId)
            ->whereRaw("jsonb_exists(details, 'zone_id') AND (details->>'zone_id') ~ '^[0-9]+$' AND (details->>'zone_id')::int = ?", [$zoneId])
            ->orderByDesc('created_at')
            ->orderByDesc('id')
            ->get(['id', 'task_name', 'status', 'details', 'created_at']);

        if ($rows->isEmpty()) {
            return null;
        }

        $latest = $rows->first();
        $details = $this->normalizeDetails($latest->details);
        $payload = $this->normalizeTaskPayload($details, $taskId, 'scheduler_logs');
        $payload['status'] = (string) ($details['status'] ?? $latest->status ?? 'unknown');
        $payload['lifecycle'] = $this->buildLifecycle($taskId, $zoneId, $rows);
        $payload['timeline'] = $this->buildTaskTimeline(
            $zoneId,
            (string) ($payload['task_id'] ?? $taskId),
            is_string($payload['correlation_id'] ?? null) ? $payload['correlation_id'] : null
        );

        return $payload;
    }

    /**
     * @param  \Illuminate\Support\Collection<int, SchedulerLog>|null  $preparedRows
     * @return array<int, array<string,mixed>>
     */
    private function buildLifecycle(string $taskId, int $zoneId, $preparedRows = null): array
    {
        $rows = $preparedRows;
        if ($rows === null) {
            $rows = SchedulerLog::query()
                ->where('task_name', 'ae_scheduler_task_'.$taskId)
                ->whereRaw("jsonb_exists(details, 'zone_id') AND (details->>'zone_id') ~ '^[0-9]+$' AND (details->>'zone_id')::int = ?", [$zoneId])
                ->orderBy('created_at')
                ->orderBy('id')
                ->get(['id', 'status', 'details', 'created_at']);
        } else {
            $rows = $rows->sortBy('created_at')->values();
        }

        return $rows->map(function (SchedulerLog $row): array {
            $details = $this->normalizeDetails($row->details);

            return [
                'status' => (string) ($details['status'] ?? $row->status ?? 'unknown'),
                'at' => $row->created_at?->toIso8601String(),
                'error' => $details['error'] ?? null,
                'source' => 'scheduler_logs',
            ];
        })->all();
    }

    /**
     * @param  \Illuminate\Support\Collection<int, SchedulerLog>  $rows
     * @return array<int, array<string,mixed>>
     */
    private function aggregateTaskRows($rows, int $limit, int $zoneId, bool $includeTimeline = false): array
    {
        $bucket = [];

        foreach ($rows as $row) {
            $details = $this->normalizeDetails($row->details);
            $taskId = (string) ($details['task_id'] ?? str_replace('ae_scheduler_task_', '', (string) $row->task_name));
            if ($taskId === '') {
                continue;
            }

            if (! isset($bucket[$taskId])) {
                $bucket[$taskId] = [
                    'payload' => $this->normalizeTaskPayload($details, $taskId, 'scheduler_logs'),
                    'updated_at' => $row->created_at,
                    'updated_id' => (int) ($row->id ?? 0),
                    'lifecycle' => [],
                ];
            }

            $bucket[$taskId]['lifecycle'][] = [
                'status' => (string) ($details['status'] ?? $row->status ?? 'unknown'),
                'at' => $row->created_at?->toIso8601String(),
                'error' => $details['error'] ?? null,
                'source' => 'scheduler_logs',
            ];

            $rowId = (int) ($row->id ?? 0);
            $isNewerTimestamp = $row->created_at && $bucket[$taskId]['updated_at'] && $row->created_at->gt($bucket[$taskId]['updated_at']);
            $isSameTimestampButNewerId = $row->created_at
                && $bucket[$taskId]['updated_at']
                && $row->created_at->equalTo($bucket[$taskId]['updated_at'])
                && $rowId > (int) ($bucket[$taskId]['updated_id'] ?? 0);

            if ($isNewerTimestamp || $isSameTimestampButNewerId) {
                $bucket[$taskId]['payload'] = $this->normalizeTaskPayload($details, $taskId, 'scheduler_logs');
                $bucket[$taskId]['updated_at'] = $row->created_at;
                $bucket[$taskId]['updated_id'] = $rowId;
            }
        }

        $items = collect($bucket)
            ->map(function (array $entry): array {
                usort($entry['lifecycle'], static fn (array $a, array $b): int => strcmp((string) ($a['at'] ?? ''), (string) ($b['at'] ?? '')));

                $payload = $entry['payload'];
                $payload['lifecycle'] = $entry['lifecycle'];
                $payload['timeline'] = [];

                return $payload;
            })
            ->sortByDesc('updated_at')
            ->take($limit)
            ->values()
            ->all();

        if ($includeTimeline) {
            foreach ($items as &$item) {
                $item['timeline'] = $this->buildTaskTimeline(
                    $zoneId,
                    (string) ($item['task_id'] ?? ''),
                    is_string($item['correlation_id'] ?? null) ? $item['correlation_id'] : null
                );
            }
            unset($item);
        }

        return $items;
    }

    /**
     * @return array<int, array<string,mixed>>
     */
    private function buildTaskTimeline(int $zoneId, string $taskId, ?string $correlationId, int $limit = 200): array
    {
        $normalizedTaskId = trim($taskId);
        $normalizedCorrelationId = is_string($correlationId) ? trim($correlationId) : '';
        if ($normalizedTaskId === '' && $normalizedCorrelationId === '') {
            return [];
        }

        $payloadColumn = $this->zoneEventPayloadColumn();
        $safeLimit = max(1, min($limit, 500));

        $rows = DB::table('zone_events')
            ->where('zone_id', $zoneId)
            ->whereIn('type', self::TASK_TIMELINE_EVENT_TYPES)
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
            $eventType = is_string($details['event_type'] ?? null) && $details['event_type'] !== ''
                ? $details['event_type']
                : (string) ($row->type ?? 'unknown');

            $eventSeq = null;
            if (isset($details['event_seq']) && is_numeric($details['event_seq'])) {
                $eventSeq = (int) $details['event_seq'];
            }

            $eventIdRaw = $details['event_id'] ?? $details['ws_event_id'] ?? $row->id;
            $actionRequired = $this->normalizeOptionalBool($details['action_required'] ?? null);

            return [
                'event_id' => (string) $eventIdRaw,
                'event_seq' => $eventSeq,
                'event_type' => $eventType,
                'type' => (string) ($row->type ?? $eventType),
                'at' => $this->toIso8601($row->created_at ?? null),
                'task_id' => is_string($details['task_id'] ?? null) ? $details['task_id'] : $normalizedTaskId,
                'correlation_id' => is_string($details['correlation_id'] ?? null) ? $details['correlation_id'] : ($normalizedCorrelationId !== '' ? $normalizedCorrelationId : null),
                'task_type' => is_string($details['task_type'] ?? null) ? $details['task_type'] : null,
                'action_required' => $actionRequired,
                'decision' => is_string($details['decision'] ?? null) ? $details['decision'] : null,
                'reason_code' => is_string($details['reason_code'] ?? null) ? $details['reason_code'] : null,
                'reason' => is_string($details['reason'] ?? null) ? $details['reason'] : null,
                'node_uid' => is_string($details['node_uid'] ?? null) ? $details['node_uid'] : null,
                'channel' => is_string($details['channel'] ?? null) ? $details['channel'] : null,
                'cmd' => is_string($details['cmd'] ?? null) ? $details['cmd'] : null,
                'status' => is_string($details['status'] ?? null) ? $details['status'] : null,
                'error_code' => is_string($details['error_code'] ?? null) ? $details['error_code'] : null,
                'details' => $details,
                'source' => 'zone_events',
            ];
        })->values()->all();
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

        return [
            'task_id' => (string) ($raw['task_id'] ?? $taskId),
            'zone_id' => isset($raw['zone_id']) ? (int) $raw['zone_id'] : null,
            'task_type' => $raw['task_type'] ?? null,
            'status' => $raw['status'] ?? null,
            'created_at' => $raw['created_at'] ?? null,
            'updated_at' => $raw['updated_at'] ?? null,
            'scheduled_for' => $raw['scheduled_for'] ?? null,
            'correlation_id' => $raw['correlation_id'] ?? null,
            'result' => $result,
            'action_required' => $actionRequired,
            'decision' => $decision,
            'reason_code' => $reasonCode,
            'reason' => $reason,
            'error' => is_string($raw['error'] ?? null) ? $raw['error'] : null,
            'error_code' => is_string($raw['error_code'] ?? null) ? $raw['error_code'] : null,
            'source' => $source,
        ];
    }

    private function zoneEventPayloadColumn(): string
    {
        return Schema::hasColumn('zone_events', 'payload_json') ? 'payload_json' : 'details';
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
