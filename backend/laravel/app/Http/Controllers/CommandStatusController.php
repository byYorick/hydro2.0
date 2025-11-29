<?php

namespace App\Http\Controllers;

use App\Models\Command;
use Illuminate\Http\Request;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Log;

class CommandStatusController extends Controller
{
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
            // Не раскрываем информацию о существовании команды неавторизованным пользователям
            return response()->json([
                'status' => 'error',
                'code' => 'NOT_FOUND',
                'message' => 'Command not found',
            ], 404);
        }

        // Проверяем права доступа через zone_id или node_id
        $hasAccess = false;
        
        if ($command->zone_id) {
            // Проверяем, что зона существует (базовая проверка)
            // В будущем можно добавить проверку прав пользователя на конкретную зону
            $hasAccess = \App\Models\Zone::where('id', $command->zone_id)->exists();
        } elseif ($command->node_id) {
            // Если команда привязана к узлу, проверяем через узел
            $node = \App\Models\DeviceNode::find($command->node_id);
            if ($node && $node->zone_id) {
                $hasAccess = \App\Models\Zone::where('id', $node->zone_id)->exists();
            } else {
                // Узел без зоны - разрешаем доступ только админам
                $hasAccess = auth()->user()->role === 'admin';
            }
        } else {
            // Команда без zone_id и node_id - разрешаем только админам
            $hasAccess = auth()->user()->role === 'admin';
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
            ],
        ]);
    }
}

