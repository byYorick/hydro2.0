<?php

namespace App\Services;

use App\Models\Alert;
use App\Models\Zone;
use App\Services\CropDay\DliDayBalance;
use DateTimeZone;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\Response;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class ZoneAutomationStateService
{
    public const STATE_CACHE_TTL_SECONDS = 300;

    private const CONTROL_MODE_FALLBACK_BACKOFF_SECONDS = 120;

    public function __construct(
        private readonly AutomationRuntimeConfigService $runtimeConfig,
        private readonly ErrorCodeCatalogService $errorCodeCatalog,
        private readonly AlertPolicyService $alertPolicy,
        private readonly ZoneAutomationObservabilityService $observabilityService,
        private readonly DliDayBalance $dliDayBalance,
    ) {}

    /**
     * Live snapshot для API и deferred Inertia prop: AE → cache → decorated payload.
     *
     * @return array<string,mixed>
     *
     * @throws ConnectionException
     * @throws RequestException
     * @throws \RuntimeException
     */
    public function resolveForApi(Zone $zone): array
    {
        try {
            $payload = $this->fetchAutomationStateFromAutomationEngine($zone->id);
            $this->cacheState($zone->id, $payload);

            return $this->decorateStatePayload($payload, false, 'live', $zone);
        } catch (ConnectionException|RequestException $e) {
            Log::warning('ZoneAutomationStateService: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            $cachedPayload = $this->getCachedState($zone->id);
            if ($cachedPayload !== null) {
                Log::info('ZoneAutomationStateService: returning cached state snapshot', [
                    'zone_id' => $zone->id,
                    'source' => 'cache',
                    'reason' => 'upstream_unavailable',
                ]);

                return $this->decorateStatePayload($cachedPayload, true, 'cache', $zone);
            }

            throw $e;
        } catch (\Throwable $e) {
            Log::warning('ZoneAutomationStateService: unexpected upstream error', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            $cachedPayload = $this->getCachedState($zone->id);
            if ($cachedPayload !== null) {
                Log::info('ZoneAutomationStateService: returning cached state snapshot', [
                    'zone_id' => $zone->id,
                    'source' => 'cache',
                    'reason' => 'unexpected_upstream_error',
                ]);

                return $this->decorateStatePayload($cachedPayload, true, 'cache', $zone);
            }

            throw $e;
        }
    }

    /**
     * Синхронный bootstrap для Inertia SSR: последний успешный snapshot из cache (без вызова AE).
     *
     * @return array<string,mixed>|null
     */
    public function resolveCachedBootstrap(Zone $zone): ?array
    {
        $cachedPayload = $this->getCachedState($zone->id);
        if ($cachedPayload === null) {
            return null;
        }

        return $this->decorateStatePayload($cachedPayload, true, 'cache', $zone);
    }

    /**
     * Deferred Inertia prop: live с cache-fallback; null если данных нет.
     *
     * @return array<string,mixed>|null
     */
    public function resolve(Zone $zone): ?array
    {
        try {
            return $this->resolveForApi($zone);
        } catch (\Throwable $e) {
            Log::warning('ZoneAutomationStateService: deferred resolve failed', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return null;
        }
    }

    public function invalidateZoneStateCache(int $zoneId): void
    {
        if ($zoneId <= 0) {
            return;
        }

        Cache::forget($this->stateCacheKey($zoneId));
    }

    /**
     * @return array<string,mixed>
     */
    private function fetchAutomationStateFromAutomationEngine(int $zoneId): array
    {
        $cfg = $this->runtimeConfig->schedulerConfig();
        $apiUrl = (string) ($cfg['api_url'] ?? config('services.automation_engine.api_url'));
        $timeout = (float) ($cfg['timeout_sec'] ?? 2.0);

        /** @var Response $response */
        $response = Http::acceptJson()
            ->timeout($timeout)
            ->retry(2, 150, function ($exception) {
                return $exception instanceof ConnectionException;
            }, false)
            ->withHeaders($this->automationEngineHeaders())
            ->get("{$apiUrl}/zones/{$zoneId}/state");

        if ($response->status() === 404) {
            Log::debug('ZoneAutomationStateService: state endpoint not found, using AE3 control-mode compatibility fallback', [
                'zone_id' => $zoneId,
                'api_url' => $apiUrl,
            ]);

            return $this->buildCompatibilityStateFromControlMode($zoneId, $apiUrl, $timeout);
        }

        $response->throw();

        $payload = $response->json();
        if (! is_array($payload)) {
            throw new \RuntimeException('automation_engine_invalid_payload');
        }

        if (! array_key_exists('zone_id', $payload)) {
            $payload['zone_id'] = $zoneId;
        }

        return $payload;
    }

    /**
     * @return array<string,mixed>
     */
    private function buildCompatibilityStateFromControlMode(int $zoneId, string $apiUrl, float $timeout): array
    {
        $controlMode = 'auto';
        $workflowPhase = 'idle';
        $currentStage = null;
        $allowedManualSteps = [];

        if (! Cache::has($this->controlModeFallbackBackoffKey($zoneId))) {
            try {
                /** @var Response $response */
                $response = Http::acceptJson()
                    ->timeout($timeout)
                    ->retry(2, 150, function ($exception) {
                        return $exception instanceof ConnectionException;
                    }, false)
                    ->withHeaders($this->automationEngineHeaders())
                    ->get("{$apiUrl}/zones/{$zoneId}/control-mode");

                if ($response->successful()) {
                    $payload = $response->json();
                    if (is_array($payload)) {
                        $data = $payload['data'] ?? $payload;
                        if (is_array($data)) {
                            $rawControlMode = strtolower((string) ($data['control_mode'] ?? 'auto'));
                            if (in_array($rawControlMode, ['auto', 'semi', 'manual'], true)) {
                                $controlMode = $rawControlMode;
                            }

                            $workflowPhase = strtolower((string) ($data['workflow_phase'] ?? 'idle'));
                            $currentStage = isset($data['current_stage']) ? (string) $data['current_stage'] : null;
                            $allowedManualSteps = isset($data['allowed_manual_steps']) && is_array($data['allowed_manual_steps'])
                                ? $data['allowed_manual_steps']
                                : [];
                        }
                    }
                    Cache::forget($this->controlModeFallbackBackoffKey($zoneId));
                } else {
                    Cache::put(
                        $this->controlModeFallbackBackoffKey($zoneId),
                        true,
                        now()->addSeconds(self::CONTROL_MODE_FALLBACK_BACKOFF_SECONDS)
                    );
                    Log::warning('ZoneAutomationStateService: control-mode fallback request failed, enabling backoff', [
                        'zone_id' => $zoneId,
                        'status' => $response->status(),
                        'api_url' => $apiUrl,
                        'backoff_seconds' => self::CONTROL_MODE_FALLBACK_BACKOFF_SECONDS,
                    ]);
                }
            } catch (\Throwable $e) {
                Cache::put(
                    $this->controlModeFallbackBackoffKey($zoneId),
                    true,
                    now()->addSeconds(self::CONTROL_MODE_FALLBACK_BACKOFF_SECONDS)
                );
                Log::warning('ZoneAutomationStateService: control-mode fallback unavailable, enabling backoff and using idle snapshot', [
                    'zone_id' => $zoneId,
                    'error' => $e->getMessage(),
                    'api_url' => $apiUrl,
                    'backoff_seconds' => self::CONTROL_MODE_FALLBACK_BACKOFF_SECONDS,
                ]);
            }
        }

        $state = $this->mapWorkflowPhaseToAutomationState($workflowPhase);
        $lastTaskState = $this->fetchLastTaskStateFromDatabase($zoneId);

        if ($currentStage === null && is_string($lastTaskState['current_stage'] ?? null)) {
            $currentStage = $lastTaskState['current_stage'];
        }
        if ($workflowPhase === 'idle' && is_string($lastTaskState['workflow_phase'] ?? null)) {
            $workflowPhase = strtolower($lastTaskState['workflow_phase']);
        }

        if (in_array($controlMode, ['manual', 'semi'], true) && is_string($currentStage) && $currentStage !== '') {
            $allowedManualSteps = $this->allowedManualStepsForStage($currentStage);
        }

        $stateLabel = $this->automationStateLabel($state);
        if (($lastTaskState['failed'] ?? false) === true) {
            $failedHeadline = is_string($lastTaskState['human_error_message'] ?? null)
                ? trim((string) $lastTaskState['human_error_message'])
                : '';
            if ($failedHeadline !== '') {
                $stateLabel = $failedHeadline;
            }
        }

        return [
            'zone_id' => $zoneId,
            'state' => $state,
            'state_label' => $stateLabel,
            'state_details' => $this->buildCompatibilityStateDetails(
                $lastTaskState,
                $currentStage,
                $workflowPhase,
            ),
            'system_config' => [
                'tanks_count' => 2,
                'system_type' => 'drip',
                'clean_tank_capacity_l' => null,
                'nutrient_tank_capacity_l' => null,
            ],
            'current_levels' => [
                'clean_tank_level_percent' => 0,
                'nutrient_tank_level_percent' => 0,
                'buffer_tank_level_percent' => null,
                'ph' => null,
                'ec' => null,
            ],
            'active_processes' => [
                'pump_in' => false,
                'circulation_pump' => false,
                'ph_correction' => false,
                'ec_correction' => false,
            ],
            'timeline' => [],
            'next_state' => null,
            'estimated_completion_sec' => null,
            'control_mode' => $controlMode,
            'control_mode_available' => ['auto', 'semi', 'manual'],
            'workflow_phase' => $workflowPhase,
            'current_stage' => $currentStage,
            'current_stage_label' => $this->automationStageLabel($currentStage),
            'allowed_manual_steps' => $allowedManualSteps,
            'compatibility' => [
                'source' => 'ae3_control_mode_fallback',
            ],
        ];
    }

    /**
     * @return array{
     *     failed: bool,
     *     error_code: ?string,
     *     error_message: ?string,
     *     human_error_message: ?string,
     *     created_at: ?string,
     *     stage_entered_at: ?string,
     *     workflow_phase: ?string,
     *     current_stage: ?string,
     *     status: ?string
     * }
     */
    private function fetchLastTaskStateFromDatabase(int $zoneId): array
    {
        try {
            $row = DB::selectOne(
                'SELECT status, error_code, error_message, created_at, stage_entered_at, workflow_phase, current_stage
                 FROM ae_tasks
                 WHERE zone_id = ? ORDER BY updated_at DESC, id DESC LIMIT 1',
                [$zoneId]
            );

            if ($row === null) {
                return [
                    'failed' => false,
                    'error_code' => null,
                    'error_message' => null,
                    'human_error_message' => null,
                    'created_at' => null,
                    'stage_entered_at' => null,
                    'workflow_phase' => null,
                    'current_stage' => null,
                    'status' => null,
                ];
            }

            $presentation = $this->errorCodeCatalog->present(
                is_string($row->error_code ?? null) ? $row->error_code : null,
                is_string($row->error_message ?? null) ? $row->error_message : null,
            );

            return [
                'failed' => $row->status === 'failed',
                'error_code' => $row->error_code,
                'error_message' => $row->error_message,
                'human_error_message' => $presentation['message'],
                'created_at' => $row->created_at,
                'stage_entered_at' => $row->stage_entered_at,
                'workflow_phase' => $row->workflow_phase,
                'current_stage' => $row->current_stage,
                'status' => $row->status,
            ];
        } catch (\Throwable $e) {
            Log::warning('ZoneAutomationStateService: could not fetch last task state from DB', [
                'zone_id' => $zoneId,
                'error' => $e->getMessage(),
            ]);

            return [
                'failed' => false,
                'error_code' => null,
                'error_message' => null,
                'human_error_message' => null,
                'created_at' => null,
                'stage_entered_at' => null,
                'workflow_phase' => null,
                'current_stage' => null,
                'status' => null,
            ];
        }
    }

    /**
     * @return array{
     *     task_id: ?int,
     *     failed_at: ?string,
     *     error_code: ?string,
     *     error_message: ?string,
     *     human_error_message: ?string
     * }|null
     */
    private function fetchLastTerminalFailure(int $zoneId): ?array
    {
        try {
            $row = DB::selectOne(
                'SELECT id, error_code, error_message, completed_at, updated_at
                 FROM ae_tasks
                 WHERE zone_id = ?
                   AND status = ?
                 ORDER BY COALESCE(completed_at, updated_at) DESC, id DESC
                 LIMIT 1',
                [$zoneId, 'failed'],
            );

            if ($row === null) {
                return null;
            }

            $presentation = $this->errorCodeCatalog->present(
                is_string($row->error_code ?? null) ? $row->error_code : null,
                is_string($row->error_message ?? null) ? $row->error_message : null,
            );

            $failedAt = $row->completed_at ?? $row->updated_at;

            return [
                'task_id' => isset($row->id) ? (int) $row->id : null,
                'failed_at' => $failedAt !== null ? (string) $failedAt : null,
                'error_code' => is_string($row->error_code ?? null) ? $row->error_code : null,
                'error_message' => is_string($row->error_message ?? null) ? $row->error_message : null,
                'human_error_message' => $presentation['message'],
            ];
        } catch (\Throwable $e) {
            Log::warning('ZoneAutomationStateService: could not fetch last terminal failure', [
                'zone_id' => $zoneId,
                'error' => $e->getMessage(),
            ]);

            return null;
        }
    }

    /**
     * @param  array<string,mixed>  $lastTaskState
     * @return array<string,mixed>
     */
    private function buildCompatibilityStateDetails(
        array $lastTaskState,
        ?string $currentStage,
        string $workflowPhase,
    ): array {
        $isFailed = ($lastTaskState['failed'] ?? false) === true;
        $anchorRaw = $lastTaskState['stage_entered_at'] ?? $lastTaskState['created_at'] ?? null;
        $elapsedSec = 0;
        $startedAt = null;
        $stageEnteredAt = null;

        if ($anchorRaw !== null) {
            try {
                $anchor = \Illuminate\Support\Carbon::parse((string) $anchorRaw);
                $elapsedSec = max(0, $anchor->diffInSeconds(now()));
                $startedAt = $anchor->toIso8601String();
                if ($lastTaskState['stage_entered_at'] ?? null) {
                    $stageEnteredAt = \Illuminate\Support\Carbon::parse((string) $lastTaskState['stage_entered_at'])->toIso8601String();
                }
            } catch (\Throwable) {
                $startedAt = is_string($anchorRaw) ? $anchorRaw : null;
            }
        }

        $stageKey = strtolower(trim((string) ($currentStage ?? $lastTaskState['current_stage'] ?? '')));
        $phaseKey = strtolower(trim($workflowPhase !== 'idle'
            ? $workflowPhase
            : (string) ($lastTaskState['workflow_phase'] ?? 'idle')));

        $activeStatuses = ['pending', 'claimed', 'running', 'waiting_command'];
        $status = strtolower((string) ($lastTaskState['status'] ?? ''));
        $progressPercent = 0;
        if (! $isFailed && in_array($status, $activeStatuses, true)) {
            $progressPercent = $this->estimateCompatibilityProgressPercent($stageKey, $phaseKey);
        }

        return [
            'started_at' => $startedAt,
            'stage_entered_at' => $stageEnteredAt,
            'elapsed_sec' => $elapsedSec,
            'progress_percent' => $progressPercent,
            'failed' => $isFailed,
            'error_code' => $lastTaskState['error_code'] ?? null,
            'error_message' => $lastTaskState['error_message'] ?? null,
            'human_error_message' => $lastTaskState['human_error_message'] ?? null,
        ];
    }

    private function estimateCompatibilityProgressPercent(string $currentStage, string $workflowPhase): int
    {
        $stageOrder = [
            'startup',
            'clean_fill_start',
            'clean_fill_check',
            'clean_fill_stop_to_solution',
            'solution_fill_start',
            'solution_fill_check',
            'solution_fill_stop_to_prepare',
            'prepare_recirculation_start',
            'prepare_recirculation_check',
            'complete_ready',
            'await_ready',
            'decision_gate',
            'irrigation_start',
            'irrigation_check',
            'irrigation_recovery_start',
            'irrigation_recovery_check',
            'completed_run',
        ];

        if ($currentStage !== '' && in_array($currentStage, $stageOrder, true)) {
            $index = array_search($currentStage, $stageOrder, true);

            return min(99, (int) round((($index + 1) / count($stageOrder)) * 100));
        }

        return match ($workflowPhase) {
            'tank_filling' => 20,
            'tank_recirc' => 45,
            'ready' => 65,
            'irrigating' => 85,
            'irrig_recirc' => 95,
            default => 0,
        };
    }

    /**
     * @return list<string>
     */
    private function allowedManualStepsForStage(string $stage): array
    {
        $normalized = strtolower(trim($stage));

        return match ($normalized) {
            'startup' => ['clean_fill_start', 'solution_fill_start', 'force_solution_fill_start'],
            'clean_fill_start', 'clean_fill_check' => ['clean_fill_stop'],
            'solution_fill_start', 'solution_fill_check' => ['solution_fill_stop'],
            'prepare_recirculation_start', 'prepare_recirculation_check' => ['prepare_recirculation_stop'],
            'irrigation_start', 'irrigation_check' => ['irrigation_stop'],
            'irrigation_recovery_check' => ['irrigation_recovery_stop'],
            default => [],
        };
    }

    private function automationStageLabel(?string $stage): ?string
    {
        if ($stage === null || trim($stage) === '') {
            return null;
        }

        return match (strtolower(trim($stage))) {
            'startup' => 'Инициализация',
            'clean_fill_start' => 'Запуск наполнения чистой водой',
            'clean_fill_check' => 'Наполнение чистой водой',
            'solution_fill_start' => 'Запуск наполнения раствором',
            'solution_fill_check' => 'Наполнение раствором',
            'prepare_recirculation_start' => 'Запуск рециркуляции',
            'prepare_recirculation_check' => 'Подготовка рециркуляции',
            'complete_ready' => 'Готов к поливу',
            'irrigation_start' => 'Запуск полива',
            'irrigation_check' => 'Полив',
            'irrigation_recovery_check' => 'Рециркуляция после полива',
            default => null,
        };
    }

    private function mapWorkflowPhaseToAutomationState(string $workflowPhase): string
    {
        return match (strtolower($workflowPhase)) {
            'tank_filling' => 'TANK_FILLING',
            'tank_recirc' => 'TANK_RECIRC',
            'ready' => 'READY',
            'irrigating' => 'IRRIGATING',
            'irrig_recirc' => 'IRRIG_RECIRC',
            default => 'IDLE',
        };
    }

    private function automationStateLabel(string $state): string
    {
        return match ($state) {
            'TANK_FILLING' => 'Наполнение баков',
            'TANK_RECIRC' => 'Рециркуляция раствора',
            'READY' => 'Раствор готов',
            'IRRIGATING' => 'Полив',
            'IRRIG_RECIRC' => 'Рециркуляция после полива',
            default => 'Ожидание',
        };
    }

    /**
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>
     */
    private function decorateStatePayload(array $payload, bool $isStale, string $source, Zone $zone): array
    {
        $stateDetails = is_array($payload['state_details'] ?? null) ? $payload['state_details'] : null;
        if ($stateDetails !== null) {
            $presentation = $this->errorCodeCatalog->present(
                is_string($stateDetails['error_code'] ?? null) ? $stateDetails['error_code'] : null,
                is_string($stateDetails['error_message'] ?? null) ? $stateDetails['error_message'] : null,
            );
            $stateDetails['human_error_message'] = $presentation['message'];
            $payload['state_details'] = $stateDetails;
        }

        if ($zone->id > 0) {
            $payload = $this->clearAcknowledgedTerminalFailure((int) $zone->id, $payload);
        }

        $payload = $this->enrichPayloadWithZoneControlMode($payload, $zone);
        $payload['day_balance'] = $this->dayBalance($zone);
        $payload = $this->observabilityService->enrichPayload((int) $zone->id, $payload, $isStale);
        $payload['last_terminal_failure'] = $this->fetchLastTerminalFailure((int) $zone->id);

        $payload['state_meta'] = [
            'source' => $source,
            'is_stale' => $isStale,
            'served_at' => now()->toIso8601String(),
        ];

        return $payload;
    }

    /**
     * Commanded-полив за местные сутки теплицы. Только чтение.
     *
     * @return array{
     *     local_date: string,
     *     window_start: string,
     *     window_end: string,
     *     timezone_fallback: bool,
     *     irrigation_commands: int,
     *     commanded_sec: float,
     *     commanded_ml: float|null,
     *     commanded_ml_status: string,
     *     dli_mol: float|null,
     *     dli_status: string
     * }
     */
    private function dayBalance(Zone $zone): array
    {
        $window = $this->greenhouseLocalDayWindow($zone);
        $row = DB::selectOne(
            "SELECT
                COUNT(*)::int AS irrigation_commands,
                COALESCE(SUM(c.duration_ms), 0)::numeric / 1000.0 AS commanded_sec,
                COUNT(*) FILTER (WHERE cal.ml_per_sec IS NULL)::int AS missing_calibration,
                SUM((c.duration_ms::numeric / 1000.0) * cal.ml_per_sec) AS commanded_ml
             FROM commands AS c
             INNER JOIN ae_commands AS ac
                ON ac.external_id = c.id::text
             INNER JOIN ae_tasks AS t
                ON t.id = ac.task_id
               AND t.task_type = 'irrigation_start'
             LEFT JOIN LATERAL (
                SELECT pc.ml_per_sec
                FROM node_channels AS nc
                INNER JOIN pump_calibrations AS pc
                    ON pc.node_channel_id = nc.id
                WHERE nc.node_id = c.node_id
                  AND nc.channel = c.channel
                  AND pc.is_active IS TRUE
                  AND pc.ml_per_sec IS NOT NULL
                  AND pc.valid_from <= ?
                  AND (pc.valid_to IS NULL OR pc.valid_to > ?)
                ORDER BY pc.valid_from DESC, pc.id DESC
                LIMIT 1
             ) AS cal ON TRUE
             WHERE c.status = 'DONE'
               AND c.zone_id = ?
               AND c.created_at >= ?
               AND c.created_at <= ?
               AND (
                    ac.planner_step = 'irrigation_start'
                    OR ac.planner_step LIKE 'irrigation\\_start%' ESCAPE '\\'
               )
               AND ac.planner_step NOT LIKE 'clean\\_fill%' ESCAPE '\\'
               AND ac.planner_step NOT LIKE 'solution\\_fill%' ESCAPE '\\'
               AND ac.planner_step NOT LIKE 'prepare\\_recirculation%' ESCAPE '\\'
               AND ac.planner_step NOT LIKE 'solution\\_topup%' ESCAPE '\\'",
            [
                $window['as_of'],
                $window['as_of'],
                (int) $zone->id,
                $window['start'],
                $window['end'],
            ],
        );

        $missingCalibration = (int) ($row->missing_calibration ?? 0);
        $commandedMl = null;
        if ($missingCalibration === 0) {
            $commandedMl = $row === null || $row->commanded_ml === null
                ? 0.0
                : round((float) $row->commanded_ml, 6);
        }

        return [
            'local_date' => $window['local_date'],
            'window_start' => $window['window_start'],
            'window_end' => $window['window_end'],
            'timezone_fallback' => $window['timezone_fallback'],
            'irrigation_commands' => (int) ($row->irrigation_commands ?? 0),
            'commanded_sec' => round((float) ($row->commanded_sec ?? 0), 3),
            'commanded_ml' => $commandedMl,
            'commanded_ml_status' => $missingCalibration === 0 ? 'ok' : 'calibration_missing',
            ...$this->dliDayBalance->forZone($zone, $window),
        ];
    }

    /**
     * @return array{
     *     local_date: string,
     *     window_start: string,
     *     window_end: string,
     *     timezone_fallback: bool,
     *     start: string,
     *     end: string,
     *     as_of: string
     * }
     */
    private function greenhouseLocalDayWindow(Zone $zone): array
    {
        $timezoneName = trim((string) ($zone->greenhouse?->timezone ?? ''));
        $timezoneFallback = $timezoneName === '';
        $timezone = new DateTimeZone('UTC');
        if (! $timezoneFallback) {
            try {
                $timezone = new DateTimeZone($timezoneName);
            } catch (\Throwable) {
                $timezoneFallback = true;
            }
        }

        $end = now()->copy()->utc();
        $local = $end->copy()->timezone($timezone);
        $localDate = $local->toDateString();
        $start = $local->copy()->startOfDay()->utc();

        return [
            'local_date' => $localDate,
            'window_start' => $start->toIso8601String(),
            'window_end' => $end->toIso8601String(),
            'timezone_fallback' => $timezoneFallback,
            'start' => $start->format('Y-m-d H:i:s'),
            'end' => $end->format('Y-m-d H:i:s'),
            'as_of' => $end->format('Y-m-d H:i:s'),
        ];
    }

    /**
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>
     */
    private function enrichPayloadWithZoneControlMode(array $payload, Zone $zone): array
    {
        $fromDb = strtolower(trim((string) ($zone->control_mode ?? '')));
        if (in_array($fromDb, ['auto', 'semi', 'manual'], true)) {
            $payload['control_mode'] = $fromDb;
        }

        $available = $payload['control_mode_available'] ?? null;
        if (! is_array($available) || $available === []) {
            $payload['control_mode_available'] = ['auto', 'semi', 'manual'];
        }

        return $payload;
    }

    /**
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>
     */
    private function clearAcknowledgedTerminalFailure(int $zoneId, array $payload): array
    {
        if ($this->zoneHasActivePolicyManagedAlerts($zoneId)) {
            return $payload;
        }

        $stateDetails = is_array($payload['state_details'] ?? null) ? $payload['state_details'] : [];
        if (($stateDetails['failed'] ?? false) !== true) {
            return $payload;
        }

        $stateDetails['failed'] = false;
        $stateDetails['error_code'] = null;
        $stateDetails['error_message'] = null;
        $stateDetails['human_error_message'] = null;
        $payload['state_details'] = $stateDetails;
        $payload['state_label'] = $this->resolveStateLabelWithoutTerminalFailure($payload);

        return $payload;
    }

    private function zoneHasActivePolicyManagedAlerts(int $zoneId): bool
    {
        $whitelist = array_values(array_filter(array_unique(array_map(
            static fn (string $code): string => strtolower(trim($code)),
            $this->alertPolicy->policyManagedCodes(),
        ))));

        if ($whitelist === []) {
            return false;
        }

        return Alert::query()
            ->where('zone_id', $zoneId)
            ->where('status', 'ACTIVE')
            ->whereIn(DB::raw('LOWER(code)'), $whitelist)
            ->exists();
    }

    /**
     * @param  array<string,mixed>  $payload
     */
    private function resolveStateLabelWithoutTerminalFailure(array $payload): string
    {
        $currentStage = isset($payload['current_stage']) ? (string) $payload['current_stage'] : null;
        $stageLabel = $this->automationStageLabel($currentStage);
        if ($stageLabel !== null) {
            return $stageLabel;
        }

        $state = is_string($payload['state'] ?? null) ? (string) $payload['state'] : 'IDLE';

        return $this->automationStateLabel($state);
    }

    /**
     * @param  array<string,mixed>  $payload
     */
    public function cacheState(int $zoneId, array $payload): void
    {
        Cache::put(
            $this->stateCacheKey($zoneId),
            $payload,
            now()->addSeconds(self::STATE_CACHE_TTL_SECONDS)
        );
    }

    /**
     * @return array<string,mixed>|null
     */
    public function getCachedState(int $zoneId): ?array
    {
        $cached = Cache::get($this->stateCacheKey($zoneId));
        if (! is_array($cached)) {
            return null;
        }

        return $cached;
    }

    public function stateCacheKey(int $zoneId): string
    {
        return "zone_automation_state:{$zoneId}";
    }

    private function controlModeFallbackBackoffKey(int $zoneId): string
    {
        return "zone_automation_state:control_mode_backoff:{$zoneId}";
    }

    /**
     * @return array<string,string>
     */
    private function automationEngineHeaders(): array
    {
        $cfg = $this->runtimeConfig->schedulerConfig();

        $headers = [
            'X-Trace-Id' => Str::lower((string) Str::uuid()),
            'X-Scheduler-Id' => (string) ($cfg['scheduler_id'] ?? 'laravel-api'),
        ];

        $token = trim((string) ($cfg['token'] ?? ''));
        if ($token !== '') {
            $headers['Authorization'] = 'Bearer '.$token;
        }

        return $headers;
    }
}
