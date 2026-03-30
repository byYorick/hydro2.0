<?php

namespace App\Http\Controllers;

use App\Models\Command;
use App\Helpers\ZoneAccessHelper;
use App\Services\AutomationRuntimeConfigService;
use App\Services\ErrorCodeCatalogService;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\Http;
use Illuminate\Http\Request;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Log;

class CommandStatusController extends Controller
{
    public function __construct(
        private readonly ErrorCodeCatalogService $errorCodeCatalog,
        private readonly AutomationRuntimeConfigService $runtimeConfig,
    ) {}

    /**
     * Получить статус команды.
     * 
     * Проверяет права доступа: команда должна принадлежать зоне, к которой пользователь имеет доступ.
     * Если команда не имеет zone_id, проверяется node_id.
     */
    public function show(Request $request, string $cmdId): JsonResponse
    {
        // Проверяем авторизацию
        if (!auth()->check()) {
            return response()->json([
                'status' => 'error',
                'code' => 'UNAUTHENTICATED',
                'message' => 'Authentication required',
            ], 401);
        }

        $command = Command::where('cmd_id', $cmdId)->first();

        if (!$command) {
            if (preg_match('/^ae3-task-(\d+)$/', $cmdId, $matches) === 1) {
                return $this->proxyAe3TaskStatus($request, (int) $matches[1], $cmdId);
            }

            // Не раскрываем информацию о существовании команды неавторизованным пользователям
            return response()->json([
                'status' => 'error',
                'code' => 'NOT_FOUND',
                'message' => 'Command not found',
            ], 404);
        }

        // Проверяем права доступа через zone_id или node_id
        $user = auth()->user();
        $hasAccess = false;
        
        if ($command->zone_id) {
            // Проверяем доступ к зоне через ZoneAccessHelper
            $hasAccess = ZoneAccessHelper::canAccessZone($user, $command->zone_id);
        } elseif ($command->node_id) {
            // Если команда привязана к узлу, проверяем через узел
            $hasAccess = ZoneAccessHelper::canAccessNode($user, $command->node_id);
        } else {
            // Команда без zone_id и node_id - разрешаем только админам
            $hasAccess = $user->isAdmin();
        }

        if (!$hasAccess) {
            Log::warning('CommandStatusController: Unauthorized access attempt', [
                'user_id' => auth()->id(),
                'cmd_id' => $cmdId,
                'command_zone_id' => $command->zone_id,
                'command_node_id' => $command->node_id,
            ]);
            
            return response()->json([
                'status' => 'error',
                'code' => 'FORBIDDEN',
                'message' => 'Access denied',
            ], 403);
        }

        return response()->json([
            'status' => 'ok',
            'data' => [
                'cmd_id' => $command->cmd_id,
                'status' => $command->status,
                'cmd' => $command->cmd,
                'ack_at' => $command->ack_at?->toIso8601String(),
                'failed_at' => $command->failed_at?->toIso8601String(),
                'sent_at' => $command->sent_at?->toIso8601String(),
                'error_code' => $command->error_code,
                'error_message' => $command->error_message,
                'human_error_message' => $this->errorCodeCatalog->present($command->error_code, $command->error_message)['message'],
                'result_code' => $command->result_code,
                'duration_ms' => $command->duration_ms,
            ],
        ]);
    }

    private function proxyAe3TaskStatus(Request $request, int $taskId, string $cmdId): JsonResponse
    {
        try {
            $cfg = $this->runtimeConfig->schedulerConfig();
            $apiUrl = (string) ($cfg['api_url'] ?? 'http://automation-engine:9405');
            $timeout = (float) ($cfg['timeout_sec'] ?? 2.0);
            $token = trim((string) ($cfg['token'] ?? ''));
            $headers = $token !== '' ? ['Authorization' => 'Bearer '.$token] : [];

            $response = Http::acceptJson()
                ->timeout($timeout)
                ->withHeaders($headers)
                ->get("{$apiUrl}/internal/tasks/{$taskId}");

            if ($response->status() === 404) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'NOT_FOUND',
                    'message' => 'Command not found',
                ], 404);
            }

            $response->throw();
            $payload = $response->json();
            $data = is_array($payload) && is_array($payload['data'] ?? null) ? $payload['data'] : [];
            $zoneId = isset($data['zone_id']) ? (int) $data['zone_id'] : null;
            if ($zoneId === null || ! ZoneAccessHelper::canAccessZone($request->user(), $zoneId)) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'FORBIDDEN',
                    'message' => 'Access denied',
                ], 403);
            }
            $status = strtoupper((string) ($data['status'] ?? 'QUEUED'));
            if ($status === 'COMPLETED') {
                $status = 'DONE';
            } elseif ($status === 'FAILED') {
                $status = 'FAILED';
            } elseif (in_array($status, ['PENDING', 'CLAIMED', 'RUNNING', 'WAITING_COMMAND'], true)) {
                $status = 'QUEUED';
            }

            return response()->json([
                'status' => 'ok',
                'data' => [
                    'cmd_id' => $cmdId,
                    'status' => $status,
                    'cmd' => 'FORCE_IRRIGATION',
                    'ack_at' => $data['completed_at'] ?? null,
                    'failed_at' => ($data['status'] ?? null) === 'failed' ? ($data['updated_at'] ?? null) : null,
                    'sent_at' => $data['created_at'] ?? null,
                    'error_code' => $data['error_code'] ?? null,
                    'error_message' => $data['error_message'] ?? null,
                    'human_error_message' => $this->errorCodeCatalog->present(
                        $data['error_code'] ?? null,
                        $data['error_message'] ?? null
                    )['message'],
                    'result_code' => null,
                    'duration_ms' => null,
                ],
            ]);
        } catch (ConnectionException $e) {
            Log::warning('CommandStatusController: AE3 task status unavailable', [
                'cmd_id' => $cmdId,
                'task_id' => $taskId,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_UNAVAILABLE',
                'message' => 'Automation-engine недоступен.',
            ], 503);
        }
    }
}
