<?php

namespace App\Http\Controllers;

use App\Events\TelemetryBatchUpdated;
use App\Http\Requests\Internal\TelemetryBatchRequest;
use Illuminate\Http\JsonResponse;

class InternalRealtimeController extends Controller
{
    public function telemetryBatch(TelemetryBatchRequest $request): JsonResponse
    {
        $maxBytes = (int) config('realtime.telemetry_batch_max_bytes');
        if ($maxBytes > 0) {
            $rawContent = $request->getContent();
            $payloadSize = is_string($rawContent) ? strlen($rawContent) : 0;
            if ($payloadSize > $maxBytes) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Payload too large',
                    'max_bytes' => $maxBytes,
                ], 413);
            }
        }

        $payload = $request->validated();
        $updates = $payload['updates'] ?? [];
        if ($updates === []) {
            return response()->json([
                'status' => 'ok',
                'broadcasted' => 0,
                'updates' => 0,
            ]);
        }

        $updatesByZone = [];
        foreach ($updates as $update) {
            $zoneId = (int) $update['zone_id'];
            $channel = $update['channel'] ?? null;
            if ($channel === '') {
                $channel = null;
            }

            $updatesByZone[$zoneId][] = [
                'node_id' => (int) $update['node_id'],
                'channel' => $channel,
                'metric_type' => (string) $update['metric_type'],
                'value' => (float) $update['value'],
                'ts' => (int) $update['timestamp'],
            ];
        }

        foreach ($updatesByZone as $zoneId => $zoneUpdates) {
            event(new TelemetryBatchUpdated($zoneId, $zoneUpdates));
        }

        return response()->json([
            'status' => 'ok',
            'broadcasted' => count($updatesByZone),
            'updates' => count($updates),
        ]);
    }
}
