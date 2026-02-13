<?php

namespace App\Http\Controllers;

use App\Models\NodeChannel;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class NodeChannelController extends Controller
{
    /**
     * Сервисное обновление config канала (для history-logger/python-сервисов).
     */
    public function serviceUpdateConfig(Request $request, NodeChannel $nodeChannel): JsonResponse
    {
        $data = $request->validate([
            'config' => ['required', 'array'],
        ]);

        $nodeChannel->config = $data['config'];
        $nodeChannel->save();

        return response()->json([
            'status' => 'ok',
            'data' => [
                'id' => $nodeChannel->id,
                'updated_at' => $nodeChannel->updated_at?->toIso8601String(),
            ],
        ]);
    }
}
