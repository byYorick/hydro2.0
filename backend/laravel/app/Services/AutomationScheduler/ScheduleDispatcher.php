<?php

namespace App\Services\AutomationScheduler;

use App\Services\AlertService;
use App\Services\AutomationConfigDocumentService;
use App\Services\ZoneAutomationIntentService;
use Carbon\CarbonImmutable;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\Pool;
use Illuminate\Http\Client\Response;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class ScheduleDispatcher
{
    use ResolvesAutomationRuntime;

    private const ZONE_BUSY_ERRORS = [
        'start_cycle_zone_busy',
        'start_irrigation_zone_busy',
        'start_lighting_tick_zone_busy',
        'start_solution_topup_zone_busy',
        'start_solution_change_zone_busy',
    ];

    private const SETUP_NOT_READY_ERRORS = [
        'start_irrigation_setup_pending',
        'start_solution_topup_not_ready',
        'solution_change_zone_not_ready',
    ];

    private const ZONE_SETUP_PENDING_REASON = 'zone_setup_pending';

    public function __construct(
        private readonly ActiveTaskStore $activeTaskStore,
        private readonly ActiveTaskPoller $activeTaskPoller,
        private readonly ZoneAutomationIntentService $intentService,
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
        $results = $this->dispatchBatch(
            jobs: [[
                'zoneId' => $zoneId,
                'schedule' => $schedule,
                'triggerTime' => $triggerTime,
                'scheduleKey' => $scheduleKey,
            ]],
            context: $context,
            writeLog: $writeLog,
        );

        return $results[0] ?? [
            'dispatched' => false,
            'retryable' => true,
            'reason' => 'dispatch_batch_result_missing',
        ];
    }

    /**
     * @param  array<int, array{
     *     zoneId:int,
     *     schedule:ScheduleItem,
     *     triggerTime:CarbonImmutable,
     *     scheduleKey:string
     * }>  $jobs
     * @return array<int, array{dispatched: bool, retryable: bool, reason: string}>
     */
    public function dispatchBatch(
        array $jobs,
        ScheduleCycleContext $context,
        callable $writeLog,
    ): array {
        $results = [];
        $preparedByIndex = [];

        foreach ($jobs as $index => $job) {
            $prepared = $this->prepareDispatch(
                zoneId: (int) $job['zoneId'],
                schedule: $job['schedule'],
                triggerTime: $job['triggerTime'],
                scheduleKey: (string) $job['scheduleKey'],
                context: $context,
                writeLog: $writeLog,
            );
            if (! (bool) ($prepared['ready'] ?? false)) {
                $results[$index] = $prepared['result'];

                continue;
            }
            $preparedByIndex[$index] = $prepared;
        }

        if ($preparedByIndex === []) {
            ksort($results);

            return $results;
        }

        $responses = [];
        try {
            $poolResults = Http::pool(function (Pool $pool) use ($preparedByIndex): void {
                foreach ($preparedByIndex as $index => $prepared) {
                    $pool
                        ->as((string) $index)
                        ->acceptJson()
                        ->timeout($prepared['timeout_sec'])
                        ->withHeaders($prepared['headers'])
                        ->post($prepared['url'], $prepared['request_payload']);
                }
            });

            foreach ($preparedByIndex as $index => $_prepared) {
                $responses[$index] = [
                    'response' => $poolResults[(string) $index] ?? null,
                    'error' => null,
                ];
            }
        } catch (\Throwable $poolError) {
            foreach ($preparedByIndex as $index => $prepared) {
                try {
                    $response = Http::acceptJson()
                        ->timeout($prepared['timeout_sec'])
                        ->withHeaders($prepared['headers'])
                        ->post($prepared['url'], $prepared['request_payload']);
                    $responses[$index] = [
                        'response' => $response,
                        'error' => null,
                    ];
                } catch (ConnectionException $e) {
                    $responses[$index] = [
                        'response' => null,
                        'error' => $e->getMessage(),
                    ];
                }
            }
        }

        foreach ($preparedByIndex as $index => $prepared) {
            /** @var Response|null $response */
            $response = $responses[$index]['response'] ?? null;
            $results[$index] = $this->finalizePreparedDispatch(
                prepared: $prepared,
                response: $response,
                connectionErrorMessage: $responses[$index]['error'] ?? null,
                writeLog: $writeLog,
            );
        }

        ksort($results);

        return $results;
    }

    /**
     * @return array<string, mixed>
     */
    private function prepareDispatch(
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
                'ready' => false,
                'result' => [
                    'dispatched' => false,
                    'retryable' => false,
                    'reason' => 'unsupported_task_type',
                ],
            ];
        }

        if (! $this->isSchedulerTaskTypeDispatchableForAe3($taskType)) {
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
                'ready' => false,
                'result' => [
                    'dispatched' => false,
                    'retryable' => false,
                    'reason' => 'ae3_task_type_not_supported',
                ],
            ];
        }

        if ($this->resolveZoneControlModeFromContext($context, $zoneId) === 'manual') {
            $writeLog(
                SchedulerRuntimeHelper::scheduleTaskLogName($zoneId, $taskType),
                'skipped',
                [
                    'zone_id' => $zoneId,
                    'task_type' => $taskType,
                    'reason' => 'control_mode_manual',
                    'automation_runtime' => $this->resolveAutomationRuntime($zoneId, 'laravel scheduler dispatch'),
                ],
            );

            return [
                'ready' => false,
                'result' => [
                    'dispatched' => false,
                    'retryable' => false,
                    'reason' => 'control_mode_manual',
                ],
            ];
        }

        if ($this->activeTaskPoller->isScheduleBusy(
            scheduleKey: $scheduleKey,
            cfg: $cfg,
            reconciledBusyness: $context->reconciledBusyness,
            writeLog: $writeLog,
        )) {
            return [
                'ready' => false,
                'result' => [
                    'dispatched' => false,
                    'retryable' => true,
                    'reason' => 'schedule_busy',
                ],
            ];
        }

        $zoneWorkflowPhase = $this->resolveZoneWorkflowPhaseFromContext(
            context: $context,
            zoneId: $zoneId,
        );
        if ($this->shouldSkipIrrigationDispatchForSetupPending($taskType, $zoneWorkflowPhase)) {
            $writeLog(
                SchedulerRuntimeHelper::scheduleTaskLogName($zoneId, $taskType),
                'skipped',
                [
                    'zone_id' => $zoneId,
                    'task_type' => $taskType,
                    'reason' => self::ZONE_SETUP_PENDING_REASON,
                    'workflow_phase' => $zoneWorkflowPhase ?? 'missing',
                    'automation_runtime' => $this->resolveAutomationRuntime($zoneId, 'laravel scheduler dispatch'),
                ],
            );

            return [
                'ready' => false,
                'result' => [
                    'dispatched' => false,
                    'retryable' => true,
                    'reason' => self::ZONE_SETUP_PENDING_REASON,
                ],
            ];
        }

        $taskName = SchedulerRuntimeHelper::scheduleTaskLogName($zoneId, $taskType);
        $payload = $schedule->payload;
        $lightingDesiredState = null;
        if ($taskType === 'lighting') {
            $resolvedDesired = $this->resolveLightingDesiredState($payload);
            if (! $resolvedDesired['ok']) {
                $writeLog($taskName, 'skipped', [
                    'zone_id' => $zoneId,
                    'task_type' => $taskType,
                    'reason' => $resolvedDesired['reason'],
                    'desired_state' => $payload['desired_state'] ?? null,
                ]);

                return [
                    'ready' => false,
                    'result' => [
                        'dispatched' => false,
                        'retryable' => false,
                        'reason' => $resolvedDesired['reason'],
                    ],
                ];
            }
            $lightingDesiredState = $resolvedDesired['state'];
        }
        $scheduledForIso = SchedulerRuntimeHelper::toIso($triggerTime);
        $correlationAnchor = $scheduledForIso;
        if (is_string($payload['catchup_original_trigger_time'] ?? null)) {
            $rawCatchupTrigger = (string) $payload['catchup_original_trigger_time'];
            $parsedCatchupTrigger = $this->parseIsoDateTime($rawCatchupTrigger);
            if ($parsedCatchupTrigger !== null) {
                $correlationAnchor = SchedulerRuntimeHelper::toIso($parsedCatchupTrigger);
            }
        } else {
            $intervalSec = ScheduleSpecHelper::safePositiveInt($schedule->intervalSec);
            if ($intervalSec > 0) {
                $intervalTaskName = SchedulerRuntimeHelper::intervalTaskLogNameForSchedule($schedule);
                $lastCompleted = $context->lastRunByTaskName[$intervalTaskName] ?? null;
                $slot = SchedulerRuntimeHelper::intervalSlotAt(
                    now: $triggerTime,
                    intervalSec: $intervalSec,
                    lastCompletedAt: $lastCompleted instanceof CarbonImmutable ? $lastCompleted : null,
                );
                $correlationAnchor = SchedulerRuntimeHelper::toIso($slot);
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
                'ready' => false,
                'result' => [
                    'dispatched' => false,
                    'retryable' => true,
                    'reason' => 'intent_upsert_failed',
                ],
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
        } elseif ($taskType === 'lighting') {
            $endpoint = '/start-lighting-tick';
            $desiredState = $lightingDesiredState ?? 'on';
            $requestPayload['desired_state'] = $desiredState;

            $brightness = $this->resolveLightingBrightnessPct($payload, $desiredState);
            if ($brightness !== null) {
                $requestPayload['brightness_pct'] = $brightness;
            }
        } elseif ($taskType === 'solution_topup') {
            $endpoint = '/start-solution-topup';
            $requestPayload['mode'] = 'normal';
            $requestPayload['trigger'] = 'periodic_tick';
        } elseif ($taskType === 'solution_change') {
            $endpoint = '/start-solution-change';
            $requestPayload['trigger'] = $this->resolveSolutionChangeTrigger($payload);
        }

        return [
            'ready' => true,
            'zone_id' => $zoneId,
            'task_type' => $taskType,
            'task_name' => $taskName,
            'schedule_key' => $scheduleKey,
            'correlation_id' => $correlationId,
            'scheduled_for_iso' => $scheduledForIso,
            'due_at_iso' => $dueAtIso,
            'expires_at_iso' => $expiresAtIso,
            'accepted_at' => $acceptedAt,
            'due_at' => $dueAt,
            'expires_at' => $expiresAt,
            'intent_snapshot' => $intentSnapshot,
            'timeout_sec' => $cfg['timeout_sec'],
            'active_task_ttl_sec' => $cfg['active_task_ttl_sec'],
            'headers' => $headers,
            'url' => $cfg['api_url'].'/zones/'.$zoneId.$endpoint,
            'request_payload' => $requestPayload,
        ];
    }

    /**
     * @return array{dispatched: bool, retryable: bool, reason: string}
     */
    private function finalizePreparedDispatch(
        array $prepared,
        ?Response $response,
        ?string $connectionErrorMessage,
        callable $writeLog,
    ): array {
        $zoneId = (int) $prepared['zone_id'];
        $taskType = (string) $prepared['task_type'];
        $taskName = (string) $prepared['task_name'];
        $scheduleKey = (string) $prepared['schedule_key'];
        $correlationId = (string) $prepared['correlation_id'];

        if ($connectionErrorMessage !== null) {
            $writeLog($taskName, 'failed', [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'error' => 'connection_error',
                'message' => $connectionErrorMessage,
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
            ]);
            $this->recordRetryableDispatchFailure(
                zoneId: $zoneId,
                correlationId: $correlationId,
                errorCode: 'scheduler_dispatch_connection_error',
                errorMessage: $connectionErrorMessage,
            );

            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'connection_error',
            ];
        }

        if (! $response instanceof Response) {
            $this->recordRetryableDispatchFailure(
                zoneId: $zoneId,
                correlationId: $correlationId,
                errorCode: 'scheduler_dispatch_connection_error',
                errorMessage: 'missing_http_response',
            );

            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'connection_error',
            ];
        }

        if (! $response->successful()) {
            $responseBody = $response->json();
            $detail = is_array($responseBody) ? ($responseBody['detail'] ?? null) : null;
            $terminalIntentErrors = [
                'start_cycle_intent_terminal',
                'start_irrigation_intent_terminal',
                'start_lighting_tick_intent_terminal',
                'start_solution_topup_intent_terminal',
                'start_solution_change_intent_terminal',
            ];
            if (
                $response->status() === 409
                && is_array($detail)
                && in_array($detail['error'] ?? null, $terminalIntentErrors, true)
            ) {
                $err = (string) ($detail['error'] ?? 'start_cycle_intent_terminal');
                $writeLog($taskName, 'failed', [
                    'zone_id' => $zoneId,
                    'task_type' => $taskType,
                    'error' => $err,
                    'status_code' => $response->status(),
                    'response' => $responseBody,
                    'schedule_key' => $scheduleKey,
                    'correlation_id' => $correlationId,
                ]);
                if ($taskType === 'irrigation' && $err === 'start_irrigation_intent_terminal') {
                    $this->raiseIrrigationWindowMissedAlert(
                        zoneId: $zoneId,
                        scheduleKey: $scheduleKey,
                        correlationId: $correlationId,
                        detail: $detail,
                    );
                }

                return [
                    'dispatched' => false,
                    'retryable' => false,
                    'reason' => $err,
                ];
            }
            if (
                $response->status() === 409
                && is_array($detail)
                && in_array(
                    $detail['error'] ?? null,
                    array_merge(self::ZONE_BUSY_ERRORS, self::SETUP_NOT_READY_ERRORS),
                    true,
                )
            ) {
                $err = (string) ($detail['error'] ?? 'start_cycle_zone_busy');
                $writeLog($taskName, 'failed', [
                    'zone_id' => $zoneId,
                    'task_type' => $taskType,
                    'error' => $err,
                    'status_code' => $response->status(),
                    'response' => $responseBody,
                    'schedule_key' => $scheduleKey,
                    'correlation_id' => $correlationId,
                ]);

                return [
                    'dispatched' => false,
                    'retryable' => true,
                    'reason' => $err,
                ];
            }
            if ($response->status() === 429) {
                $extracted = $this->extractDetailError($detail);
                $err = (is_string($extracted) && str_ends_with($extracted, '_rate_limited'))
                    ? $extracted
                    : 'rate_limited';
                $writeLog($taskName, 'failed', [
                    'zone_id' => $zoneId,
                    'task_type' => $taskType,
                    'error' => $err,
                    'status_code' => $response->status(),
                    'response' => $responseBody,
                    'schedule_key' => $scheduleKey,
                    'correlation_id' => $correlationId,
                ]);

                return [
                    'dispatched' => false,
                    'retryable' => true,
                    'reason' => $err,
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
            $this->recordRetryableDispatchFailure(
                zoneId: $zoneId,
                correlationId: $correlationId,
                errorCode: 'scheduler_dispatch_http_error',
                errorMessage: 'HTTP '.$response->status(),
            );

            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'http_error',
            ];
        }

        $body = $response->json();
        $data = is_array($body) ? ($body['data'] ?? null) : null;
        $taskIdentity = $this->resolveSubmittedTaskIdentity(
            zoneId: (int) $prepared['zone_id'],
            responseTaskId: is_array($data) ? trim((string) ($data['task_id'] ?? '')) : '',
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
            $this->recordRetryableDispatchFailure(
                zoneId: $zoneId,
                correlationId: $correlationId,
                errorCode: $taskIdError,
                errorMessage: 'AE3 response missing valid task_id',
            );

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
                'scheduled_for' => $prepared['scheduled_for_iso'],
                'due_at' => $prepared['due_at_iso'],
                'expires_at' => $prepared['expires_at_iso'],
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
                'accepted_at' => SchedulerRuntimeHelper::toIso($prepared['accepted_at']),
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
                acceptedAt: $prepared['accepted_at'],
                dueAt: $prepared['due_at'],
                expiresAt: $prepared['expires_at'],
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
            'intent_id' => $prepared['intent_snapshot']['intent_id'] ?? null,
            'scheduled_for' => $prepared['scheduled_for_iso'],
            'due_at' => $prepared['due_at_iso'],
            'expires_at' => $prepared['expires_at_iso'],
            'schedule_key' => $scheduleKey,
            'correlation_id' => $correlationId,
            'accepted_at' => SchedulerRuntimeHelper::toIso($prepared['accepted_at']),
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
            acceptedAt: $prepared['accepted_at'],
            dueAt: $prepared['due_at'],
            expiresAt: $prepared['expires_at'],
            details: $acceptedDetails,
        );

        Cache::put(
            SchedulerRuntimeHelper::activeTaskCacheKey($scheduleKey),
            [
                'task_id' => $taskId,
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'accepted_at' => SchedulerRuntimeHelper::toIso($prepared['accepted_at']),
            ],
            now()->addSeconds((int) ($prepared['active_task_ttl_sec'] ?? 180)),
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

            $topology = app(ZoneAutomationIntentService::class)->resolveAe3TopologyForZone($zoneId);

            $aeTaskType = match ($taskType) {
                'irrigation' => 'irrigation_start',
                'lighting' => 'lighting_tick',
                'solution_topup' => 'solution_topup',
                'solution_change' => 'solution_change',
                default => 'cycle_start',
            };
            $aeTopology = match ($taskType) {
                'lighting' => 'lighting_tick',
                default => $topology,
            };
            $irrigationMode = $taskType === 'irrigation' ? 'normal' : null;
            $irrigationDurationSec = null;
            if ($taskType === 'irrigation' && isset($payload['duration_sec']) && is_numeric($payload['duration_sec'])) {
                $irrigationDurationSec = max(1, (int) $payload['duration_sec']);
            }

            $intentPayloadJson = null;
            if ($taskType === 'solution_change') {
                $intentPayloadJson = json_encode([
                    'task_type' => 'solution_change',
                    'workflow' => 'solution_change',
                    'trigger' => $this->resolveSolutionChangeTrigger($payload),
                ], JSON_THROW_ON_ERROR);
            }

            $intentType = $this->mapTaskTypeToIntentType($taskType);
            $now = SchedulerRuntimeHelper::nowUtc();

            $row = DB::selectOne(
                "
                INSERT INTO zone_automation_intents (
                    zone_id,
                    intent_type,
                    task_type,
                    topology,
                    irrigation_mode,
                    irrigation_requested_duration_sec,
                    intent_source,
                    idempotency_key,
                    payload,
                    status,
                    not_before,
                    retry_count,
                    max_retries,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'laravel_scheduler', ?, ?::jsonb, 'pending', ?, 0, 3, ?, ?)
                ON CONFLICT (zone_id, idempotency_key)
                DO UPDATE SET
                    task_type = EXCLUDED.task_type,
                    topology = EXCLUDED.topology,
                    irrigation_mode = EXCLUDED.irrigation_mode,
                    irrigation_requested_duration_sec = EXCLUDED.irrigation_requested_duration_sec,
                    intent_source = EXCLUDED.intent_source,
                    payload = EXCLUDED.payload,
                    not_before = EXCLUDED.not_before,
                    updated_at = EXCLUDED.updated_at
                WHERE zone_automation_intents.status NOT IN ('completed', 'failed', 'cancelled')
                RETURNING id
                ",
                [
                    $zoneId,
                    $intentType,
                    $aeTaskType,
                    $aeTopology,
                    $irrigationMode,
                    $irrigationDurationSec,
                    $correlationId,
                    $intentPayloadJson,
                    $triggerTime,
                    $now,
                    $now,
                ],
            );
            $intentId = isset($row->id) ? (int) $row->id : null;
            if ($intentId === null || $intentId <= 0) {
                return ['ok' => false, 'intent_id' => null];
            }

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
    public function resolveSubmittedTaskIdentity(int $zoneId, string $responseTaskId): array
    {
        $automationRuntime = $this->resolveAutomationRuntime($zoneId, 'laravel scheduler dispatch');
        $taskId = trim($responseTaskId);

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
            'solution_topup' => 'SOLUTION_TOPUP_TICK',
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

    /**
     * Laravel scheduler диспатчит только поддержанные AE3 compat-path типы.
     * Runtime в БД — только ae3 (CHECK); отдельной матрицы non-ae3 нет.
     */
    private function isSchedulerTaskTypeDispatchableForAe3(string $taskType): bool
    {
        return in_array($taskType, ['irrigation', 'lighting', 'solution_topup', 'solution_change', 'diagnostics'], true);
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

    private function resolveZoneWorkflowPhaseFromContext(ScheduleCycleContext $context, int $zoneId): ?string
    {
        $phase = $context->zoneWorkflowPhases[$zoneId] ?? null;
        if (! is_string($phase)) {
            return null;
        }
        $normalized = strtolower(trim($phase));

        return $normalized === '' ? null : $normalized;
    }

    private function resolveZoneControlModeFromContext(ScheduleCycleContext $context, int $zoneId): ?string
    {
        $controlMode = $context->zoneControlModes[$zoneId] ?? null;
        if (! is_string($controlMode)) {
            return null;
        }
        $normalized = strtolower(trim($controlMode));

        return $normalized === '' ? null : $normalized;
    }

    /**
     * irrigation / solution_topup / solution_change не диспатчатся, пока workflow_phase !== ready.
     */
    private function shouldSkipIrrigationDispatchForSetupPending(string $taskType, ?string $workflowPhase): bool
    {
        if (! in_array($taskType, ['irrigation', 'solution_topup', 'solution_change'], true)) {
            return false;
        }

        return $workflowPhase !== 'ready';
    }

    /**
     * @param  array<string, mixed>  $detail
     */
    private function raiseIrrigationWindowMissedAlert(
        int $zoneId,
        string $scheduleKey,
        string $correlationId,
        array $detail,
    ): void {
        try {
            app(AlertService::class)->createOrUpdateActive([
                'zone_id' => $zoneId,
                'source' => 'biz',
                'code' => 'biz_irrigation_window_missed',
                'type' => 'Irrigation window missed',
                'status' => 'ACTIVE',
                'details' => [
                    'schedule_key' => $scheduleKey,
                    'correlation_id' => $correlationId,
                    'error' => $detail['error'] ?? 'start_irrigation_intent_terminal',
                ],
            ]);
        } catch (\Throwable $e) {
            Log::warning('Failed to raise biz_irrigation_window_missed alert', [
                'zone_id' => $zoneId,
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
                'error' => $e->getMessage(),
            ]);
        }
    }

    /**
     * @param  array<string, mixed>  $payload
     * @return array{ok: true, state: string}|array{ok: false, reason: string}
     */
    private function resolveLightingDesiredState(array $payload): array
    {
        if (! array_key_exists('desired_state', $payload) || $payload['desired_state'] === null) {
            return ['ok' => true, 'state' => 'on'];
        }

        if (! is_string($payload['desired_state']) && ! is_numeric($payload['desired_state'])) {
            return ['ok' => false, 'reason' => 'invalid_lighting_desired_state'];
        }

        $normalized = strtolower(trim((string) $payload['desired_state']));
        if ($normalized === '') {
            return ['ok' => true, 'state' => 'on'];
        }

        if (! in_array($normalized, ['on', 'off'], true)) {
            return ['ok' => false, 'reason' => 'invalid_lighting_desired_state'];
        }

        return ['ok' => true, 'state' => $normalized];
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function resolveSolutionChangeTrigger(array $payload): string
    {
        $raw = $payload['trigger'] ?? null;
        if (! is_string($raw)) {
            return 'scheduler';
        }
        $normalized = trim($raw);

        return $normalized !== '' ? $normalized : 'scheduler';
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function resolveLightingBrightnessPct(array $payload, string $desiredState): ?int
    {
        $brightnessKey = $desiredState === 'off' ? 'brightness_night' : 'brightness';
        $candidate = $payload[$brightnessKey] ?? ($desiredState === 'on' ? ($payload['brightness'] ?? null) : null);
        if (! is_numeric($candidate)) {
            return null;
        }

        return max(0, min(100, (int) $candidate));
    }

    private function extractDetailError(mixed $detail): ?string
    {
        if (is_array($detail) && is_string($detail['error'] ?? null)) {
            $error = trim((string) $detail['error']);

            return $error !== '' ? $error : null;
        }

        if (is_string($detail)) {
            $error = trim($detail);

            return $error !== '' ? $error : null;
        }

        return null;
    }

    private function recordRetryableDispatchFailure(
        int $zoneId,
        string $correlationId,
        string $errorCode,
        ?string $errorMessage = null,
    ): void {
        if (trim($correlationId) === '') {
            return;
        }

        try {
            $outcome = $this->intentService->recordSchedulerDispatchFailure(
                zoneId: $zoneId,
                idempotencyKey: $correlationId,
                errorCode: $errorCode,
                errorMessage: $errorMessage,
            );

            if (($outcome['failed'] ?? false) === true) {
                Log::warning('Scheduler intent marked failed after dispatch retries exhausted', [
                    'zone_id' => $zoneId,
                    'correlation_id' => $correlationId,
                    'error_code' => $errorCode,
                    'retry_count' => $outcome['retry_count'] ?? null,
                ]);
            }
        } catch (\Throwable $e) {
            Log::warning('Failed to record scheduler dispatch failure for intent', [
                'zone_id' => $zoneId,
                'correlation_id' => $correlationId,
                'error_code' => $errorCode,
                'error' => $e->getMessage(),
            ]);
        }
    }
}
