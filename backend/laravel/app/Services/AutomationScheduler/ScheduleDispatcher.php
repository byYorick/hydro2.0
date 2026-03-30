<?php

namespace App\Services\AutomationScheduler;

use App\Services\AutomationConfigDocumentService;
use Carbon\CarbonImmutable;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class ScheduleDispatcher
{
    use ResolvesAutomationRuntime;

    public function __construct(
        private readonly ActiveTaskStore $activeTaskStore,
        private readonly ActiveTaskPoller $activeTaskPoller,
    ) {}

    /**
     * @return array{dispatched: bool, retryable: bool, reason: string}
     */
    public function dispatch(
        int $zoneId,
        ScheduleItem $schedule,
        CarbonImmutable $triggerTime,
        string $scheduleKey,
        ScheduleCycleContext $context,
        callable $writeLog,
    ): array {
        $cfg = $context->cfg;
        $headers = $context->headers;

        $taskType = $schedule->taskType;
        if (! in_array($taskType, SchedulerConstants::SUPPORTED_TASK_TYPES, true)) {
            return [
                'dispatched' => false,
                'retryable' => false,
                'reason' => 'unsupported_task_type',
            ];
        }

        if (! $this->supportsAe3StartCycleTaskType($zoneId, $taskType)) {
            $writeLog(
                SchedulerRuntimeHelper::scheduleTaskLogName($zoneId, $taskType),
                'skipped',
                [
                    'zone_id' => $zoneId,
                    'task_type' => $taskType,
                    'reason' => 'ae3_task_type_not_supported',
                    'automation_runtime' => $this->resolveAutomationRuntime($zoneId, 'laravel scheduler dispatch'),
                ],
            );

            return [
                'dispatched' => false,
                'retryable' => false,
                'reason' => 'ae3_task_type_not_supported',
            ];
        }

        if ($this->activeTaskPoller->isScheduleBusy(
            scheduleKey: $scheduleKey,
            cfg: $cfg,
            reconciledBusyness: $context->reconciledBusyness,
            writeLog: $writeLog,
        )) {
            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'schedule_busy',
            ];
        }

        $taskName = SchedulerRuntimeHelper::scheduleTaskLogName($zoneId, $taskType);
        $payload = $schedule->payload;

        $scheduledForIso = SchedulerRuntimeHelper::toIso($triggerTime);
        $correlationAnchor = $scheduledForIso;
        if (is_string($payload['catchup_original_trigger_time'] ?? null)) {
            $rawCatchupTrigger = (string) $payload['catchup_original_trigger_time'];
            $parsedCatchupTrigger = $this->parseIsoDateTime($rawCatchupTrigger);
            if ($parsedCatchupTrigger !== null) {
                $correlationAnchor = SchedulerRuntimeHelper::toIso($parsedCatchupTrigger);
            }
        }

        $presetCorrelationId = trim((string) ($payload['correlation_id'] ?? ''));
        $correlationId = $presetCorrelationId !== ''
            ? $presetCorrelationId
            : $this->buildSchedulerCorrelationId(
                zoneId: $zoneId,
                taskType: $taskType,
                scheduledFor: $correlationAnchor,
                scheduleKey: $scheduleKey,
            );

        [$dueAtIso, $expiresAtIso] = $this->computeTaskDeadlines($triggerTime, $cfg['due_grace_sec'], $cfg['expires_after_sec']);
        $acceptedAt = SchedulerRuntimeHelper::nowUtc();
        $dueAt = $this->parseIsoDateTime($dueAtIso);
        $expiresAt = $this->parseIsoDateTime($expiresAtIso);

        $intentSnapshot = $this->upsertSchedulerIntent(
            zoneId: $zoneId,
            taskType: $taskType,
            correlationId: $correlationId,
            triggerTime: $triggerTime,
            payload: $payload,
        );
        if (! $intentSnapshot['ok']) {
            $writeLog($taskName, 'failed', [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'error' => 'intent_upsert_failed',
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
            ]);

            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'intent_upsert_failed',
            ];
        }

        $requestPayload = [
            'source' => 'laravel_scheduler',
            'idempotency_key' => $correlationId,
        ];
        $endpoint = '/start-cycle';
        if ($taskType === 'irrigation') {
            $endpoint = '/start-irrigation';
            $requestPayload['mode'] = 'normal';
            $requestPayload['requested_duration_sec'] = isset($payload['duration_sec']) && is_numeric($payload['duration_sec'])
                ? max(1, (int) $payload['duration_sec'])
                : null;
        }

        try {
            $response = Http::acceptJson()
                ->timeout($cfg['timeout_sec'])
                ->withHeaders($headers)
                ->post($cfg['api_url'].'/zones/'.$zoneId.$endpoint, $requestPayload);
        } catch (ConnectionException $e) {
            $writeLog($taskName, 'failed', [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'error' => 'connection_error',
                'message' => $e->getMessage(),
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
            ]);

            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'connection_error',
            ];
        }

        if (! $response->successful()) {
            $responseBody = $response->json();
            $detail = is_array($responseBody) ? ($responseBody['detail'] ?? null) : null;
            if (
                $response->status() === 409
                && is_array($detail)
                && (($detail['error'] ?? null) === 'start_cycle_intent_terminal')
            ) {
                $writeLog($taskName, 'failed', [
                    'zone_id' => $zoneId,
                    'task_type' => $taskType,
                    'error' => 'start_cycle_intent_terminal',
                    'status_code' => $response->status(),
                    'response' => $responseBody,
                    'schedule_key' => $scheduleKey,
                    'correlation_id' => $correlationId,
                ]);

                return [
                    'dispatched' => false,
                    'retryable' => false,
                    'reason' => 'start_cycle_intent_terminal',
                ];
            }
            $writeLog($taskName, 'failed', [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'error' => 'http_error',
                'status_code' => $response->status(),
                'response' => $response->body(),
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
            ]);

            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'http_error',
            ];
        }

        $body = $response->json();
        $data = is_array($body) ? ($body['data'] ?? null) : null;
        $taskIdentity = $this->resolveSubmittedTaskIdentity(
            zoneId: $zoneId,
            responseTaskId: is_array($data) ? trim((string) ($data['task_id'] ?? '')) : '',
            intentId: isset($intentSnapshot['intent_id']) ? (int) $intentSnapshot['intent_id'] : null,
        );
        $taskId = $taskIdentity['task_id'];
        $apiTaskStatus = is_array($data)
            ? strtolower(trim((string) (($data['task_status'] ?? null) ?? ($data['status'] ?? ''))))
            : '';
        $taskStatus = $this->normalizeSubmittedTaskStatus(
            submittedStatus: $apiTaskStatus,
            accepted: (bool) (is_array($data) ? ($data['accepted'] ?? true) : true),
        );
        $isDuplicate = (bool) (is_array($data) ? ($data['deduplicated'] ?? false) : false);
        $taskIdError = $taskIdentity['error'];

        if ($taskIdError !== null) {
            $writeLog($taskName, 'failed', [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'error' => $taskIdError,
                'automation_runtime' => $taskIdentity['automation_runtime'],
                'returned_task_id' => is_array($data) ? ($data['task_id'] ?? null) : null,
                'response' => $body,
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
            ]);

            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => $taskIdError,
            ];
        }

        $normalizedStatus = SchedulerConstants::normalizeTerminalStatus($taskStatus);
        if ($this->isTerminalStatus($normalizedStatus)) {
            $logStatus = $normalizedStatus === 'completed' ? 'completed' : 'failed';
            $terminalDetails = [
                'terminal_on_submit' => true,
                'is_duplicate' => $isDuplicate,
                'scheduled_for' => $scheduledForIso,
                'due_at' => $dueAtIso,
                'expires_at' => $expiresAtIso,
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
                'accepted_at' => SchedulerRuntimeHelper::toIso($acceptedAt),
            ];
            $writeLog($taskName, $logStatus, [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'task_id' => $taskId,
                'status' => $normalizedStatus,
                ...$terminalDetails,
            ]);
            $this->persistActiveTaskSnapshot(
                zoneId: $zoneId,
                taskId: $taskId,
                taskType: $taskType,
                scheduleKey: $scheduleKey,
                correlationId: $correlationId,
                status: $normalizedStatus,
                acceptedAt: $acceptedAt,
                dueAt: $dueAt,
                expiresAt: $expiresAt,
                details: $terminalDetails,
            );

            return [
                'dispatched' => $normalizedStatus === 'completed',
                'retryable' => false,
                'reason' => 'terminal_'.$normalizedStatus,
            ];
        }

        $acceptedDetails = [
            'deduplicated' => $isDuplicate,
            'intent_id' => $intentSnapshot['intent_id'] ?? null,
            'scheduled_for' => $scheduledForIso,
            'due_at' => $dueAtIso,
            'expires_at' => $expiresAtIso,
            'schedule_key' => $scheduleKey,
            'correlation_id' => $correlationId,
            'accepted_at' => SchedulerRuntimeHelper::toIso($acceptedAt),
        ];

        $writeLog($taskName, 'accepted', [
            'zone_id' => $zoneId,
            'task_type' => $taskType,
            'task_id' => $taskId,
            'status' => $taskStatus,
            ...$acceptedDetails,
        ]);
        $this->persistActiveTaskSnapshot(
            zoneId: $zoneId,
            taskId: $taskId,
            taskType: $taskType,
            scheduleKey: $scheduleKey,
            correlationId: $correlationId,
            status: $taskStatus,
            acceptedAt: $acceptedAt,
            dueAt: $dueAt,
            expiresAt: $expiresAt,
            details: $acceptedDetails,
        );

        Cache::put(
            SchedulerRuntimeHelper::activeTaskCacheKey($scheduleKey),
            [
                'task_id' => $taskId,
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'accepted_at' => SchedulerRuntimeHelper::toIso($acceptedAt),
            ],
            now()->addSeconds($cfg['active_task_ttl_sec']),
        );

        return [
            'dispatched' => true,
            'retryable' => false,
            'reason' => 'accepted',
        ];
    }

    /**
     * @return array{ok: bool, intent_id: int|null}
     */
    public function upsertSchedulerIntent(
        int $zoneId,
        string $taskType,
        string $correlationId,
        CarbonImmutable $triggerTime,
        array $payload = [],
    ): array {
        try {
            app(AutomationConfigDocumentService::class)->ensureZoneDefaults($zoneId);

            $intentPayload = [
                'source' => 'laravel_scheduler',
                'task_type' => $taskType === 'irrigation' ? 'irrigation_start' : $taskType,
                'workflow' => $taskType === 'irrigation' ? 'irrigation_start' : 'cycle_start',
            ];
            if ($taskType === 'irrigation') {
                $intentPayload['mode'] = 'normal';
                if (isset($payload['duration_sec']) && is_numeric($payload['duration_sec'])) {
                    $intentPayload['requested_duration_sec'] = max(1, (int) $payload['duration_sec']);
                }
            }
            $intentType = $this->mapTaskTypeToIntentType($taskType);
            $now = SchedulerRuntimeHelper::nowUtc();

            $row = DB::selectOne(
                "
                INSERT INTO zone_automation_intents (
                    zone_id,
                    intent_type,
                    payload,
                    idempotency_key,
                    status,
                    not_before,
                    retry_count,
                    max_retries,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?::jsonb, ?, 'pending', ?, 0, 3, ?, ?)
                ON CONFLICT (zone_id, idempotency_key)
                DO UPDATE SET
                    payload = EXCLUDED.payload,
                    not_before = EXCLUDED.not_before,
                    updated_at = EXCLUDED.updated_at
                WHERE zone_automation_intents.status NOT IN ('completed', 'failed', 'cancelled')
                RETURNING id
                ",
                [
                    $zoneId,
                    $intentType,
                    json_encode($intentPayload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                    $correlationId,
                    $triggerTime,
                    $now,
                    $now,
                ],
            );
            $intentId = isset($row->id) ? (int) $row->id : null;

            return ['ok' => true, 'intent_id' => $intentId];
        } catch (\Throwable $e) {
            Log::warning('Failed to upsert scheduler intent', [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'correlation_id' => $correlationId,
                'error' => $e->getMessage(),
            ]);

            return ['ok' => false, 'intent_id' => null];
        }
    }

    /**
     * @param  array<string, mixed>  $details
     */
    public function persistActiveTaskSnapshot(
        int $zoneId,
        string $taskId,
        string $taskType,
        string $scheduleKey,
        string $correlationId,
        string $status,
        CarbonImmutable $acceptedAt,
        ?CarbonImmutable $dueAt,
        ?CarbonImmutable $expiresAt,
        array $details,
    ): void {
        $this->activeTaskStore->upsertTaskSnapshot(
            taskId: $taskId,
            zoneId: $zoneId,
            taskType: $taskType,
            scheduleKey: $scheduleKey,
            correlationId: $correlationId,
            status: $status,
            acceptedAt: $acceptedAt,
            dueAt: $dueAt,
            expiresAt: $expiresAt,
            details: $details,
        );
    }

    public function buildSchedulerCorrelationId(
        int $zoneId,
        string $taskType,
        ?string $scheduledFor,
        ?string $scheduleKey,
    ): string {
        $base = sprintf(
            '%d|%s|%s|%s',
            $zoneId,
            $taskType,
            $scheduledFor ?? '',
            $scheduleKey ?? '',
        );
        $digest = substr(hash('sha256', $base), 0, 20);

        return sprintf('sch:z%d:%s:%s', $zoneId, $taskType, $digest);
    }

    /**
     * @return array{task_id: string, automation_runtime: string, error: string|null}
     */
    public function resolveSubmittedTaskIdentity(int $zoneId, string $responseTaskId, ?int $intentId): array
    {
        $automationRuntime = $this->resolveAutomationRuntime($zoneId, 'laravel scheduler dispatch');
        $taskId = trim($responseTaskId);

        if ($automationRuntime === 'ae3') {
            if ($taskId === '') {
                return [
                    'task_id' => '',
                    'automation_runtime' => $automationRuntime,
                    'error' => 'ae3_task_id_missing',
                ];
            }

            if (preg_match('/^\d+$/', $taskId) !== 1) {
                return [
                    'task_id' => '',
                    'automation_runtime' => $automationRuntime,
                    'error' => 'ae3_task_id_invalid',
                ];
            }

            return [
                'task_id' => $taskId,
                'automation_runtime' => $automationRuntime,
                'error' => null,
            ];
        }

        if ($taskId !== '') {
            return [
                'task_id' => $taskId,
                'automation_runtime' => $automationRuntime,
                'error' => null,
            ];
        }

        if ($intentId !== null && $intentId > 0) {
            return [
                'task_id' => 'intent-'.$intentId,
                'automation_runtime' => $automationRuntime,
                'error' => null,
            ];
        }

        return [
            'task_id' => '',
            'automation_runtime' => $automationRuntime,
            'error' => 'task_id_missing',
        ];
    }

    /**
     * @return array{0:string,1:string}
     */
    public function computeTaskDeadlines(CarbonImmutable $scheduledFor, int $dueGraceSec, int $expiresAfterSec): array
    {
        $dueAt = $scheduledFor->addSeconds($dueGraceSec);
        $expiresAt = $scheduledFor->addSeconds($expiresAfterSec);

        return [SchedulerRuntimeHelper::toIso($dueAt), SchedulerRuntimeHelper::toIso($expiresAt)];
    }

    public function mapTaskTypeToIntentType(string $taskType): string
    {
        // intent_type is stored for audit/debug; automation-engine executes start-cycle as diagnostics/cycle_start.
        $normalized = strtolower(trim($taskType));

        return match ($normalized) {
            'irrigation' => 'IRRIGATE_ONCE',
            'lighting' => 'LIGHTING_TICK',
            'ventilation' => 'VENTILATION_TICK',
            'solution_change' => 'SOLUTION_CHANGE_TICK',
            'mist' => 'MIST_TICK',
            default => 'DIAGNOSTICS_TICK',
        };
    }

    public function normalizeSubmittedTaskStatus(string $submittedStatus, bool $accepted): string
    {
        $status = strtolower(trim($submittedStatus));
        if ($status === '') {
            return $accepted ? 'accepted' : 'rejected';
        }

        if (in_array($status, ['pending', 'claimed', 'running', 'accepted', 'queued'], true)) {
            return 'accepted';
        }

        return SchedulerConstants::normalizeTerminalStatus($status);
    }

    private function isTerminalStatus(string $status): bool
    {
        return in_array($status, SchedulerConstants::TERMINAL_STATUSES, true);
    }

    private function supportsAe3StartCycleTaskType(int $zoneId, string $taskType): bool
    {
        $automationRuntime = $this->resolveAutomationRuntime($zoneId, 'laravel scheduler dispatch');
        if ($automationRuntime !== 'ae3') {
            return true;
        }

        return $taskType === 'irrigation';
    }

    private function parseIsoDateTime(?string $value): ?CarbonImmutable
    {
        if (! is_string($value) || trim($value) === '') {
            return null;
        }

        try {
            return CarbonImmutable::parse($value)->utc()->setMicroseconds(0);
        } catch (\Throwable) {
            return null;
        }
    }
}
