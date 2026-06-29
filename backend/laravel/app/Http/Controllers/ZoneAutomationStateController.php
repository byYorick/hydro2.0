<?php

namespace App\Http\Controllers;

use App\Http\Controllers\Concerns\PresentsLocalizedApiErrors;
use App\Helpers\ZoneAccessHelper;
use App\Models\Alert;
use App\Models\Zone;
use App\Services\AlertPolicyService;
use App\Services\AutomationRuntimeConfigService;
use App\Services\ErrorCodeCatalogService;
use App\Services\ZoneAutomationObservabilityService;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\Response;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class ZoneAutomationStateController extends Controller
{
    use PresentsLocalizedApiErrors;

    private const STATE_CACHE_TTL_SECONDS = 300;

    private const CONTROL_MODE_FALLBACK_BACKOFF_SECONDS = 120;

    public function __construct(
        private readonly AutomationRuntimeConfigService $runtimeConfig,
        private readonly ErrorCodeCatalogService $errorCodeCatalog,
        private readonly AlertPolicyService $alertPolicy,
        private readonly ZoneAutomationObservabilityService $observabilityService,
    ) {}

    public function show(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        try {
            $payload = $this->fetchAutomationStateFromAutomationEngine($zone->id);
            $this->cacheState($zone->id, $payload);

            return response()->json($this->decorateStatePayload($payload, false, 'live', $zone));
        } catch (ConnectionException|RequestException $e) {
            Log::warning('ZoneAutomationStateController: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            $cachedPayload = $this->getCachedState($zone->id);
            if ($cachedPayload !== null) {
                Log::info('ZoneAutomationStateController: returning cached state snapshot', [
                    'zone_id' => $zone->id,
                    'source' => 'cache',
                    'reason' => 'upstream_unavailable',
                ]);

                return response()->json($this->decorateStatePayload($cachedPayload, true, 'cache', $zone));
            }

            return $this->localizedError('upstream_unavailable', null, 503);
        } catch (\Throwable $e) {
            Log::warning('ZoneAutomationStateController: unexpected upstream error', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            $cachedPayload = $this->getCachedState($zone->id);
            if ($cachedPayload !== null) {
                Log::info('ZoneAutomationStateController: returning cached state snapshot', [
                    'zone_id' => $zone->id,
                    'source' => 'cache',
                    'reason' => 'unexpected_upstream_error',
                ]);

                return response()->json($this->decorateStatePayload($cachedPayload, true, 'cache', $zone));
            }

            return $this->localizedError('upstream_error', 'Ошибка при получении состояния автоматизации.', 503);
        }
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
            ->get("{$apiUrl}/zones/{$zoneId}/state");

        if ($response->status() === 404) {
            Log::debug('ZoneAutomationStateController: state endpoint not found, using AE3 control-mode compatibility fallback', [
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
     * Compatibility fallback for AE3-Lite where `/zones/{id}/state` is not exposed.
     *
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
                    Log::warning('ZoneAutomationStateController: control-mode fallback request failed, enabling backoff', [
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
                Log::warning('ZoneAutomationStateController: control-mode fallback unavailable, enabling backoff and using idle snapshot', [
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
     * Query ae_tasks directly to get the last task status for a zone.
     * Used in the control-mode fallback to surface real failed state.
     *
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
            Log::warning('ZoneAutomationStateController: could not fetch last task state from DB', [
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
     * Последний terminal failure по зоне (read-only для UI после ack алерта).
     *
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
            Log::warning('ZoneAutomationStateController: could not fetch last terminal failure', [
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
     * Канонический control_mode — `zones.control_mode` (актуально при stale cache AE).
     *
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
     * После manual ack policy-managed алерта UI не должен показывать terminal failed,
     * пока AE3 снова не поднимет ACTIVE-алерт (см. automation_block на дашборде).
     *
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

    public static function invalidateZoneStateCache(int $zoneId): void
    {
        if ($zoneId <= 0) {
            return;
        }

        Cache::forget("zone_automation_state:{$zoneId}");
    }

    /**
     * @param  array<string,mixed>  $payload
     */
    private function cacheState(int $zoneId, array $payload): void
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
    private function getCachedState(int $zoneId): ?array
    {
        $cached = Cache::get($this->stateCacheKey($zoneId));
        if (! is_array($cached)) {
            return null;
        }

        return $cached;
    }

    private function stateCacheKey(int $zoneId): string
    {
        return "zone_automation_state:{$zoneId}";
    }

    private function controlModeFallbackBackoffKey(int $zoneId): string
    {
        return "zone_automation_state:control_mode_backoff:{$zoneId}";
    }
}
