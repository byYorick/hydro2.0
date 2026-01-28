<?php

namespace App\Http\Controllers;

use App\Events\TelemetryBatchUpdated;
use App\Http\Requests\Internal\TelemetryBatchRequest;
use Illuminate\Broadcasting\BroadcastException;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Log;

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

        $broadcastErrors = 0;
        foreach ($updatesByZone as $zoneId => $zoneUpdates) {
            try {
                event(new TelemetryBatchUpdated($zoneId, $zoneUpdates));
            } catch (BroadcastException $e) {
                $broadcastErrors++;
                Log::warning('Realtime broadcast failed for telemetry batch', [
                    'zone_id' => $zoneId,
                    'error' => $e->getMessage(),
                ]);
            }
        }

        return response()->json([
            'status' => 'ok',
            'broadcasted' => count($updatesByZone) - $broadcastErrors,
            'broadcast_errors' => $broadcastErrors,
            'updates' => count($updates),
        ]);
    }
}
