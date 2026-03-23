<?php

namespace App\Http\Controllers;

use App\Models\NodeChannel;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Arr;

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

        $nodeChannel->config = $this->mergeConfig($nodeChannel->config, $data['config']);
        $nodeChannel->save();

        return response()->json([
            'status' => 'ok',
            'data' => [
                'id' => $nodeChannel->id,
                'updated_at' => $nodeChannel->updated_at?->toIso8601String(),
            ],
        ]);
    }

    /**
     * Merge service patch into stored channel config without clobbering unrelated keys.
     */
    private function mergeConfig(mixed $current, mixed $incoming): array
    {
        $currentConfig = is_array($current) ? $current : [];
        $incomingConfig = is_array($incoming) ? $incoming : [];

        return $this->mergeAssocConfig($currentConfig, $incomingConfig);
    }

    private function mergeAssocConfig(array $current, array $incoming): array
    {
        $merged = $current;

        foreach ($incoming as $key => $value) {
            $currentValue = $merged[$key] ?? null;
            if (
                is_string($key)
                && is_array($value)
                && ! Arr::isList($value)
                && is_array($currentValue)
                && ! Arr::isList($currentValue)
            ) {
                $merged[$key] = $this->mergeAssocConfig($currentValue, $value);
                continue;
            }

            $merged[$key] = $value;
        }

        return $merged;
    }
}
