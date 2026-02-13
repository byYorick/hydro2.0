<?php

namespace App\Http\Controllers;

use App\Http\Requests\StoreZoneCommandRequest;
use App\Http\Resources\CommandResource;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Models\GrowCycle;
use App\Enums\GrowCycleStatus;
use App\Services\PythonBridgeService;
use App\Services\ZoneAutomationLogicProfileService;
use App\Services\ZoneReadinessService;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\TimeoutException;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Arr;

class ZoneCommandController extends Controller
{
    public function __construct(
        private readonly ZoneAutomationLogicProfileService $automationLogicProfiles,
    ) {
    }

    /**
     * Отправка команды для зоны в Python-сервис + логирование в историю зоны.
     */
    public function store(StoreZoneCommandRequest $request, Zone $zone, PythonBridgeService $bridge): JsonResponse
    {
        // Проверяем авторизацию через Policy
        $this->authorize('sendCommand', $zone);

        $data = $request->validated();

        // Ensure params is an associative array (object), not a list
        // Python service expects Dict[str, Any], not a list
        if (! isset($data['params']) || $data['params'] === null) {
            $data['params'] = [];
        } elseif (is_array($data['params']) && array_is_list($data['params'])) {
            // Convert indexed array to empty object
            $data['params'] = [];
        }

        if (($data['type'] ?? '') === 'GROWTH_CYCLE_CONFIG') {
            $data = $this->enrichGrowthCycleConfigPayload($zone, $data);
        }

        // Бизнес-правило: в зоне может быть только один активный цикл выращивания
        if (($data['type'] ?? '') === 'GROWTH_CYCLE_CONFIG' && ($data['params']['mode'] ?? '') === 'start') {
            $hasActiveCycle = GrowCycle::query()
                ->where('zone_id', $zone->id)
                ->whereIn('status', [GrowCycleStatus::PLANNED, GrowCycleStatus::RUNNING, GrowCycleStatus::PAUSED])
                ->exists();

            if ($hasActiveCycle) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'CYCLE_ALREADY_ACTIVE',
                    'message' => 'В этой зоне уже есть активный цикл выращивания. Сначала завершите или остановите текущий цикл.',
                ], 422);
            }

            // Проверка готовности зоны к старту цикла
            $readinessService = app(ZoneReadinessService::class);
            $readiness = $readinessService->validate($zone->id);
            
            // Если есть критические ошибки - блокируем старт
            if (!$readiness['valid']) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'ZONE_NOT_READY',
                    'message' => 'Зона не готова к запуску цикла',
                    'data' => [
                        'errors' => $readiness['errors'],
                        'warnings' => $readiness['warnings'],
                    ],
                ], 422);
            }
            
            // Если есть предупреждения и не указан флаг "start_anyway" - возвращаем предупреждения
            if (!empty($readiness['warnings']) && !($data['params']['start_anyway'] ?? false)) {
                return response()->json([
                    'status' => 'warning',
                    'code' => 'ZONE_READINESS_WARNINGS',
                    'message' => 'Зона готова к запуску, но есть предупреждения',
                    'data' => [
                        'warnings' => $readiness['warnings'],
                        'can_start_anyway' => true,
                    ],
                ], 422);
            }
        }

        if (($data['type'] ?? '') === 'GROWTH_CYCLE_CONFIG' && ($data['params']['mode'] ?? '') === 'adjust') {
            $activeCycle = $this->findActiveCycle($zone);
            if ($activeCycle) {
                $requestedSystemType = Arr::get($data, 'params.subsystems.irrigation.targets.system_type');
                if (is_string($requestedSystemType) && $requestedSystemType !== '') {
                    $currentSystemType = Arr::get($activeCycle->settings ?? [], 'irrigation.system_type');
                    if (!is_string($currentSystemType) || trim($currentSystemType) === '') {
                        return response()->json([
                            'status' => 'error',
                            'code' => 'CYCLE_IRRIGATION_NOT_INITIALIZED',
                            'message' => 'Тип системы цикла не инициализирован. Создайте цикл через мастер запуска с параметрами irrigation.',
                        ], 422);
                    }

                    if ($currentSystemType !== $requestedSystemType) {
                        return response()->json([
                            'status' => 'error',
                            'code' => 'SYSTEM_TYPE_LOCKED',
                            'message' => 'Тип системы нельзя изменять в активном цикле. Он задаётся только при старте.',
                        ], 422);
                    }
                }
            }
        }

        $user = $request->user();

        try {
            $commandId = $bridge->sendZoneCommand($zone, $data);

            // Логируем запуск/коррекцию цикла выращивания и прочие команды в историю зоны
            $this->logZoneCommand($zone, $data, $commandId, $user?->id, $user?->name);

            return response()->json([
                'status' => 'ok',
                'data' => [
                    'command_id' => $commandId,
                ],
            ]);
        } catch (ConnectionException $e) {
            Log::error('ZoneCommandController: Connection error', [
                'zone_id' => $zone->id,
                'command_type' => $data['type'] ?? null,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'SERVICE_UNAVAILABLE',
                'message' => 'Unable to connect to command service. Please try again later.',
                'details' => $e->getMessage(),
            ], 503);
        } catch (TimeoutException $e) {
            Log::error('ZoneCommandController: Timeout error', [
                'zone_id' => $zone->id,
                'command_type' => $data['type'] ?? null,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'SERVICE_TIMEOUT',
                'message' => 'Command service did not respond in time. Please try again later.',
                'details' => $e->getMessage(),
            ], 503);
        } catch (RequestException $e) {
            Log::error('ZoneCommandController: Request error', [
                'zone_id' => $zone->id,
                'command_type' => $data['type'] ?? null,
                'error' => $e->getMessage(),
                'status' => $e->response?->status(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'COMMAND_FAILED',
                'message' => 'Failed to send command. The command may have been queued but failed validation.',
                'details' => $this->extractRequestExceptionDetails($e),
            ], 422);
        } catch (\InvalidArgumentException $e) {
            Log::warning('ZoneCommandController: Invalid argument', [
                'zone_id' => $zone->id,
                'command_type' => $data['type'] ?? null,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'INVALID_ARGUMENT',
                'message' => $e->getMessage(),
                'details' => $e->getMessage(),
            ], 422);
        } catch (\Exception $e) {
            Log::error('ZoneCommandController: Unexpected error', [
                'zone_id' => $zone->id,
                'command_type' => $data['type'] ?? null,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
                'trace' => $e->getTraceAsString(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'INTERNAL_ERROR',
                'message' => 'An unexpected error occurred while sending the command.',
                'details' => $e->getMessage(),
            ], 500);
        }
    }

    private function extractRequestExceptionDetails(RequestException $exception): string
    {
        $response = $exception->response;
        if (! $response) {
            return $exception->getMessage();
        }

        $json = $response->json();
        if (is_array($json)) {
            $message = $json['message'] ?? null;
            if (is_string($message) && $message !== '') {
                return $message;
            }
        }

        $body = trim((string) $response->body());
        if ($body !== '') {
            return mb_substr($body, 0, 600);
        }

        return $exception->getMessage();
    }

    private function findActiveCycle(Zone $zone): ?GrowCycle
    {
        return GrowCycle::query()
            ->where('zone_id', $zone->id)
            ->whereIn('status', [GrowCycleStatus::PLANNED, GrowCycleStatus::RUNNING, GrowCycleStatus::PAUSED])
            ->latest('started_at')
            ->first();
    }

    private function enrichGrowthCycleConfigPayload(Zone $zone, array $data): array
    {
        $params = is_array($data['params'] ?? null) ? $data['params'] : [];
        $profileMode = $params['profile_mode'] ?? null;
        if (!is_string($profileMode) || trim($profileMode) === '') {
            throw new \InvalidArgumentException('GROWTH_CYCLE_CONFIG requires params.profile_mode.');
        }

        $profile = $this->automationLogicProfiles->resolveProfileByMode($zone->id, $profileMode);
        if (!$profile) {
            throw new \InvalidArgumentException("Automation logic profile '{$profileMode}' not found for zone {$zone->id}.");
        }

        $subsystems = is_array($profile->subsystems) ? $profile->subsystems : [];
        if (empty($subsystems)) {
            throw new \InvalidArgumentException("Automation logic profile '{$profileMode}' has empty subsystems.");
        }

        $params['subsystems'] = $subsystems;
        $data['params'] = $params;

        return $data;
    }

    /**
     * Логирование команды в историю зоны через ZoneEvent.
     *
     * Формат совместим с текущим логом (details: array, created_at: datetime (UTC)).
     */
    protected function logZoneCommand(
        Zone $zone,
        array $data,
        ?string $commandId,
        ?int $userId,
        ?string $userName
    ): void {
        $type = $data['type'] ?? '';
        $params = $data['params'] ?? [];

        // Специальная обработка агрегированного цикла выращивания
        if ($type === 'GROWTH_CYCLE_CONFIG') {
            $mode = $params['mode'] ?? null;
            $eventType = match ($mode) {
                'start' => 'CYCLE_STARTED',
                'adjust' => 'CYCLE_ADJUSTED',
                default => 'CYCLE_CONFIG',
            };

            $subsystems = $params['subsystems'] ?? null;

            if ($mode === 'start') {
                // Проверяем, нет ли уже активного цикла
                $hasActiveCycle = GrowCycle::query()
                    ->where('zone_id', $zone->id)
                    ->whereIn('status', [GrowCycleStatus::PLANNED, GrowCycleStatus::RUNNING, GrowCycleStatus::PAUSED])
                    ->exists();

                if (!$hasActiveCycle) {
                    // Логируем событие, но не создаем цикл здесь
                    // Создание циклов должно происходить через GrowCycleController::store()
                    Log::warning('ZoneCommandController: GROWTH_CYCLE_CONFIG start command received, but cycle creation should use GrowCycleController::store()', [
                        'zone_id' => $zone->id,
                        'subsystems' => $subsystems,
                    ]);
                }
            }

            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => $eventType,
                'details' => [
                    'command_type' => $type,
                    'command_id' => $commandId,
                    'mode' => $mode,
                    'profile_mode' => $params['profile_mode'] ?? null,
                    'subsystems' => $subsystems,
                    'source' => 'web',
                    'user_id' => $userId,
                    'user_name' => $userName,
                ],
                'created_at' => now()->setTimezone('UTC'),
            ]);

            return;
        }

        // Общий лог для остальных команд зоны (FORCE_PH_CONTROL, FORCE_EC_CONTROL, ...)
        ZoneEvent::create([
            'zone_id' => $zone->id,
            'type' => 'ZONE_COMMAND',
            'details' => [
                'command_type' => $type,
                'command_id' => $commandId,
                'params' => $params,
                'node_uid' => $data['node_uid'] ?? null,
                'channel' => $data['channel'] ?? null,
                'source' => 'web',
                'user_id' => $userId,
                'user_name' => $userName,
            ],
            'created_at' => now()->setTimezone('UTC'),
        ]);
    }
}
