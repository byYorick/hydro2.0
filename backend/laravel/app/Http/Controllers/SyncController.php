<?php

namespace App\Http\Controllers;

use App\Models\TelemetryLast;
use App\Models\Command;
use App\Models\Alert;
use App\Helpers\ZoneAccessHelper;
use Illuminate\Http\Request;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;
use Carbon\Carbon;

/**
 * Контроллер для синхронизации состояния при переподключении WebSocket.
 * 
 * Предоставляет snapshots данных (telemetry, commands, alerts) для reconciliation
 * после переподключения клиента.
 */
class SyncController extends Controller
{
    /**
     * Получить snapshot телеметрии для всех доступных зон пользователя.
     * 
     * Возвращает последние значения телеметрии для всех зон, к которым
     * пользователь имеет доступ.
     */
    public function telemetry(Request $request): JsonResponse
    {
        if (!Auth::check()) {
            return response()->json([
                'status' => 'error',
                'code' => 'UNAUTHENTICATED',
                'message' => 'Authentication required',
            ], 401);
        }

        $user = Auth::user();
        
        // Получаем список доступных зон
        $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);
        
        if (empty($accessibleZoneIds)) {
            return response()->json([
                'status' => 'ok',
                'data' => [],
                'timestamp' => Carbon::now()->toIso8601String(),
            ]);
        }

        try {
            $telemetry = TelemetryLast::query()
                ->whereIn('zone_id', $accessibleZoneIds)
                ->get()
                ->map(function ($item) {
                    return [
                        'zone_id' => $item->zone_id,
                        'node_id' => $item->node_id,
                        'channel' => $item->channel,
                        'metric_type' => $item->metric_type,
                        'value' => $item->value,
                        'ts' => $item->ts?->toIso8601String(),
                    ];
                });

            return response()->json([
                'status' => 'ok',
                'data' => $telemetry,
                'timestamp' => Carbon::now()->toIso8601String(),
            ]);
        } catch (\Exception $e) {
            Log::error('SyncController: Error fetching telemetry snapshot', [
                'user_id' => $user->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'INTERNAL_ERROR',
                'message' => 'Failed to fetch telemetry snapshot',
            ], 500);
        }
    }

    /**
     * Получить snapshot статусов команд.
     * 
     * Возвращает активные (не завершенные) команды для всех зон,
     * к которым пользователь имеет доступ.
     */
    public function commands(Request $request): JsonResponse
    {
        if (!Auth::check()) {
            return response()->json([
                'status' => 'error',
                'code' => 'UNAUTHENTICATED',
                'message' => 'Authentication required',
            ], 401);
        }

        $user = Auth::user();
        
        // Получаем список доступных зон
        $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);
        
        try {
            $query = Command::query()
                ->whereNotIn('status', Command::FINAL_STATUSES) // Только активные команды
                ->orderBy('created_at', 'desc')
                ->limit(100); // Ограничиваем количество для производительности

            // Фильтруем по доступным зонам, если пользователь не админ
            if (!$user->isAdmin()) {
                if (empty($accessibleZoneIds)) {
                    return response()->json([
                        'status' => 'ok',
                        'data' => [],
                        'timestamp' => Carbon::now()->toIso8601String(),
                    ]);
                }
                $query->whereIn('zone_id', $accessibleZoneIds);
            }

            $commands = $query->get()->map(function ($command) {
                return [
                    'cmd_id' => $command->cmd_id,
                    'zone_id' => $command->zone_id,
                    'node_id' => $command->node_id,
                    'status' => $command->status,
                    'type' => $command->cmd,
                    'params' => $command->params,
                    'sent_at' => $command->sent_at?->toIso8601String(),
                    'ack_at' => $command->ack_at?->toIso8601String(),
                    'failed_at' => $command->failed_at?->toIso8601String(),
                    'error_code' => $command->error_code,
                    'error_message' => $command->error_message,
                    'created_at' => $command->created_at?->toIso8601String(),
                ];
            });

            return response()->json([
                'status' => 'ok',
                'data' => $commands,
                'timestamp' => Carbon::now()->toIso8601String(),
            ]);
        } catch (\Exception $e) {
            Log::error('SyncController: Error fetching commands snapshot', [
                'user_id' => $user->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'INTERNAL_ERROR',
                'message' => 'Failed to fetch commands snapshot',
            ], 500);
        }
    }

    /**
     * Получить snapshot активных алертов.
     * 
     * Возвращает активные алерты для всех зон, к которым
     * пользователь имеет доступ.
     */
    public function alerts(Request $request): JsonResponse
    {
        if (!Auth::check()) {
            return response()->json([
                'status' => 'error',
                'code' => 'UNAUTHENTICATED',
                'message' => 'Authentication required',
            ], 401);
        }

        $user = Auth::user();
        
        // Получаем список доступных зон
        $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);
        
        try {
            $query = Alert::query()
                ->select(['id', 'zone_id', 'type', 'status', 'details', 'code', 'source', 'created_at'])
                ->with('zone:id,name')
                ->where('status', 'ACTIVE')
                ->orderBy('created_at', 'desc')
                ->limit(100); // Ограничиваем количество для производительности

            // Фильтруем по доступным зонам, если пользователь не админ
            if (!$user->isAdmin()) {
                if (empty($accessibleZoneIds)) {
                    return response()->json([
                        'status' => 'ok',
                        'data' => [],
                        'timestamp' => Carbon::now()->toIso8601String(),
                    ]);
                }
                $query->whereIn('zone_id', $accessibleZoneIds);
            }

            $alerts = $query->get()->map(function ($alert) {
                return [
                    'id' => $alert->id,
                    'zone_id' => $alert->zone_id,
                    'zone' => $alert->zone ? [
                        'id' => $alert->zone->id,
                        'name' => $alert->zone->name,
                    ] : null,
                    'type' => $alert->type,
                    'code' => $alert->code,
                    'source' => $alert->source,
                    'status' => $alert->status,
                    'details' => $alert->details,
                    'created_at' => $alert->created_at?->toIso8601String(),
                ];
            });

            return response()->json([
                'status' => 'ok',
                'data' => $alerts,
                'timestamp' => Carbon::now()->toIso8601String(),
            ]);
        } catch (\Exception $e) {
            Log::error('SyncController: Error fetching alerts snapshot', [
                'user_id' => $user->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'INTERNAL_ERROR',
                'message' => 'Failed to fetch alerts snapshot',
            ], 500);
        }
    }

    /**
     * Получить полный snapshot всех данных для reconciliation.
     * 
     * Возвращает объединенный snapshot телеметрии, команд и алертов
     * в одном запросе для оптимизации.
     */
    public function full(Request $request): JsonResponse
    {
        if (!Auth::check()) {
            return response()->json([
                'status' => 'error',
                'code' => 'UNAUTHENTICATED',
                'message' => 'Authentication required',
            ], 401);
        }

        $user = Auth::user();
        
        try {
            // Получаем все snapshots параллельно
            $telemetryResponse = $this->telemetry($request);
            $commandsResponse = $this->commands($request);
            $alertsResponse = $this->alerts($request);

            // Проверяем ошибки
            if ($telemetryResponse->getStatusCode() !== 200) {
                return $telemetryResponse;
            }
            if ($commandsResponse->getStatusCode() !== 200) {
                return $commandsResponse;
            }
            if ($alertsResponse->getStatusCode() !== 200) {
                return $alertsResponse;
            }

            $telemetryData = json_decode($telemetryResponse->getContent(), true);
            $commandsData = json_decode($commandsResponse->getContent(), true);
            $alertsData = json_decode($alertsResponse->getContent(), true);

            return response()->json([
                'status' => 'ok',
                'data' => [
                    'telemetry' => $telemetryData['data'] ?? [],
                    'commands' => $commandsData['data'] ?? [],
                    'alerts' => $alertsData['data'] ?? [],
                ],
                'timestamp' => Carbon::now()->toIso8601String(),
            ]);
        } catch (\Exception $e) {
            Log::error('SyncController: Error fetching full snapshot', [
                'user_id' => $user->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'INTERNAL_ERROR',
                'message' => 'Failed to fetch full snapshot',
            ], 500);
        }
    }
}
