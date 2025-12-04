<?php

namespace App\Http\Controllers;

use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Models\ZoneCycle;
use App\Services\PythonBridgeService;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\TimeoutException;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

class ZoneCommandController extends Controller
{
    /**
     * Отправка команды для зоны в Python-сервис + логирование в историю зоны.
     */
    public function store(Request $request, Zone $zone, PythonBridgeService $bridge): JsonResponse
    {
        $data = $request->validate([
            'type' => ['required', 'string', 'max:64'],
            'params' => ['nullable'],
            'node_uid' => ['nullable', 'string', 'max:64'],
            'channel' => ['nullable', 'string', 'max:64'],
        ]);

        // Ensure params is an associative array (object), not a list
        // Python service expects Dict[str, Any], not a list
        if (! isset($data['params']) || $data['params'] === null) {
            $data['params'] = [];
        } elseif (is_array($data['params']) && array_is_list($data['params'])) {
            // Convert indexed array to empty object
            $data['params'] = [];
        }

        // Специальная валидация для GROWTH_CYCLE_CONFIG
        if ($data['type'] === 'GROWTH_CYCLE_CONFIG') {
            $params = $data['params'] ?? [];

            // Проверяем наличие mode
            if (! isset($params['mode']) || ! in_array($params['mode'], ['start', 'adjust'], true)) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'VALIDATION_ERROR',
                    'message' => 'The params.mode field is required and must be "start" or "adjust" for GROWTH_CYCLE_CONFIG.',
                ], 422);
            }

            // Проверяем наличие subsystems
            if (! isset($params['subsystems']) || ! is_array($params['subsystems'])) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'VALIDATION_ERROR',
                    'message' => 'The params.subsystems field is required and must be an object for GROWTH_CYCLE_CONFIG.',
                ], 422);
            }

            // Проверяем обязательные подсистемы (ph, ec, irrigation должны быть enabled)
            $subsystems = $params['subsystems'];
            $requiredSubsystems = ['ph', 'ec', 'irrigation'];
            foreach ($requiredSubsystems as $subsystem) {
                if (! isset($subsystems[$subsystem]) || ! is_array($subsystems[$subsystem])) {
                    return response()->json([
                        'status' => 'error',
                        'code' => 'VALIDATION_ERROR',
                        'message' => "The params.subsystems.{$subsystem} field is required for GROWTH_CYCLE_CONFIG.",
                    ], 422);
                }
                
                if (! isset($subsystems[$subsystem]['enabled']) || $subsystems[$subsystem]['enabled'] !== true) {
                    return response()->json([
                        'status' => 'error',
                        'code' => 'VALIDATION_ERROR',
                        'message' => "The params.subsystems.{$subsystem}.enabled must be true (required subsystem).",
                    ], 422);
                }
                
                // Если enabled, должны быть targets
                if ($subsystems[$subsystem]['enabled'] && ! isset($subsystems[$subsystem]['targets'])) {
                    return response()->json([
                        'status' => 'error',
                        'code' => 'VALIDATION_ERROR',
                        'message' => "The params.subsystems.{$subsystem}.targets field is required when enabled.",
                    ], 422);
                }
            }

            // Бизнес-правило: в зоне может быть только один активный цикл выращивания
            if ($params['mode'] === 'start') {
                $hasActiveCycle = ZoneCycle::query()
                    ->where('zone_id', $zone->id)
                    ->where('status', 'active')
                    ->exists();

                if ($hasActiveCycle) {
                    return response()->json([
                        'status' => 'error',
                        'code' => 'CYCLE_ALREADY_ACTIVE',
                        'message' => 'В этой зоне уже есть активный цикл выращивания. Сначала завершите или остановите текущий цикл.',
                    ], 422);
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
            ], 500);
        }
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

            // Управление моделью ZoneCycle
            if ($mode === 'start') {
                // Создаем новый активный цикл
                ZoneCycle::create([
                    'zone_id' => $zone->id,
                    'type' => 'GROWTH_CYCLE',
                    'status' => 'active',
                    'subsystems' => $subsystems,
                    'started_at' => now()->setTimezone('UTC'),
                    'ends_at' => null,
                ]);
            } elseif ($mode === 'adjust') {
                // Обновляем текущий активный цикл (если есть)
                $activeCycle = ZoneCycle::query()
                    ->where('zone_id', $zone->id)
                    ->where('status', 'active')
                    ->latest('started_at')
                    ->first();

                if ($activeCycle) {
                    $activeCycle->update([
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
