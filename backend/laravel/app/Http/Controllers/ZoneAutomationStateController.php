<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Services\AutomationRuntimeConfigService;
use App\Services\ErrorCodeCatalogService;
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
    private const STATE_CACHE_TTL_SECONDS = 300;
    private const CONTROL_MODE_FALLBACK_BACKOFF_SECONDS = 120;

    public function __construct(
        private readonly AutomationRuntimeConfigService $runtimeConfig,
        private readonly ErrorCodeCatalogService $errorCodeCatalog,
    ) {
    }

    public function show(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        try {
            $payload = $this->fetchAutomationStateFromAutomationEngine($zone->id);
            $this->cacheState($zone->id, $payload);

            return response()->json($this->decorateStatePayload($payload, false, 'live'));
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

                return response()->json($this->decorateStatePayload($cachedPayload, true, 'cache'));
            }

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_UNAVAILABLE',
                'message' => 'Automation-engine недоступен.',
            ], 503);
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

                return response()->json($this->decorateStatePayload($cachedPayload, true, 'cache'));
            }

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_ERROR',
                'message' => 'Ошибка при получении состояния автоматизации.',
            ], 503);
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

        return [
            'zone_id' => $zoneId,
            'state' => $state,
            'state_label' => $this->automationStateLabel($state),
            'state_details' => [
                'started_at' => $lastTaskState['created_at'] ?? null,
                'elapsed_sec' => 0,
                'progress_percent' => 0,
                'failed' => $lastTaskState['failed'] ?? false,
                'error_code' => $lastTaskState['error_code'] ?? null,
                'error_message' => $lastTaskState['error_message'] ?? null,
                'human_error_message' => $lastTaskState['human_error_message'] ?? null,
            ],
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
            'workflow_phase' => $workflowPhase,
            'current_stage' => $currentStage,
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
     * @return array{failed: bool, error_code: ?string, error_message: ?string, human_error_message: ?string, created_at: ?string}
     */
    private function fetchLastTaskStateFromDatabase(int $zoneId): array
    {
        try {
            $row = DB::selectOne(
                'SELECT status, error_code, error_message, created_at FROM ae_tasks
                 WHERE zone_id = ? ORDER BY updated_at DESC, id DESC LIMIT 1',
                [$zoneId]
            );

            if ($row === null) {
                return ['failed' => false, 'error_code' => null, 'error_message' => null, 'human_error_message' => null, 'created_at' => null];
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
            ];
        } catch (\Throwable $e) {
            Log::warning('ZoneAutomationStateController: could not fetch last task state from DB', [
                'zone_id' => $zoneId,
                'error' => $e->getMessage(),
            ]);

            return ['failed' => false, 'error_code' => null, 'error_message' => null, 'human_error_message' => null, 'created_at' => null];
        }
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
    private function decorateStatePayload(array $payload, bool $isStale, string $source): array
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

        $payload['state_meta'] = [
            'source' => $source,
            'is_stale' => $isStale,
            'served_at' => now()->toIso8601String(),
        ];

        return $payload;
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
