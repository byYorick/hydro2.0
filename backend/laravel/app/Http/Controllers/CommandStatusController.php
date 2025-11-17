<?php

namespace App\Http\Controllers;

use App\Models\Command;
use Illuminate\Http\Request;
use Illuminate\Http\JsonResponse;

class CommandStatusController extends Controller
{
    public function show(Request $request, string $cmdId): JsonResponse
    {
        $command = Command::where('cmd_id', $cmdId)->first();

        if (!$command) {
            return response()->json([
                'status' => 'not_found',
                'message' => 'Command not found',
            ], 404);
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

