<?php

namespace App\Http\Controllers;

use App\Models\DeviceNode;
use Carbon\Carbon;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Response;

class PythonIngestController extends Controller
{
    private function ensureToken(Request $request): void
    {
        $expected = Config::get('services.python_bridge.ingest_token') ?? Config::get('services.python_bridge.token');
        $given = $request->bearerToken();
        
        // Если токен не настроен, всегда требуем токен (даже в testing)
        // Это обеспечивает безопасность по умолчанию
        if (!$expected) {
            throw new \Illuminate\Http\Exceptions\HttpResponseException(
                response()->json([
                    'status' => 'error',
                    'message' => 'Unauthorized: service token not configured',
                ], 401)
            );
        }
        
        if (!$given || !hash_equals($expected, (string) $given)) {
            throw new \Illuminate\Http\Exceptions\HttpResponseException(
                response()->json([
                    'status' => 'error',
                    'message' => 'Unauthorized: invalid or missing service token',
                ], 401)
            );
        }
    }

    public function telemetry(Request $request)
    {
        $this->ensureToken($request);
        $data = $request->validate([
            'zone_id' => ['required', 'integer', 'exists:zones,id'],
            'node_id' => ['nullable', 'integer', 'exists:nodes,id'],
            'metric_type' => ['required', 'string', 'max:64'],
            'value' => ['required', 'numeric'],
            'ts' => ['nullable', 'date'],
            'channel' => ['nullable', 'string', 'max:64'],
        ]);

        // Проверяем, что zone_id существует
        $zone = \App\Models\Zone::find($data['zone_id']);
        if (!$zone) {
            \Illuminate\Support\Facades\Log::warning('PythonIngestController: Zone not found', [
                'zone_id' => $data['zone_id'],
            ]);
            return \Illuminate\Support\Facades\Response::json([
                'status' => 'error',
                'message' => 'Zone not found',
            ], 404);
        }

        // Получаем node_uid из БД и проверяем привязку node_id→zone_id
        $nodeUid = null;
        $nodeId = $data['node_id'] ?? null;
        if ($nodeId) {
            $node = DeviceNode::find($nodeId);
            if (!$node) {
                \Illuminate\Support\Facades\Log::warning('PythonIngestController: Node not found', [
                    'node_id' => $nodeId,
                ]);
                return \Illuminate\Support\Facades\Response::json([
                    'status' => 'error',
                    'message' => 'Node not found',
                ], 404);
            }
            
            // Проверяем, что нода привязана к указанной зоне
            if ($node->zone_id !== $data['zone_id']) {
                \Illuminate\Support\Facades\Log::warning('PythonIngestController: Node zone mismatch', [
                    'node_id' => $nodeId,
                    'node_zone_id' => $node->zone_id,
                    'requested_zone_id' => $data['zone_id'],
                ]);
                return \Illuminate\Support\Facades\Response::json([
                    'status' => 'error',
                    'message' => 'Node is not assigned to the specified zone',
                ], 422);
            }
            
            $nodeUid = $node->uid;
        }
        $tsValue = $data['ts'] ?? null;
        $timestamp = $tsValue ? Carbon::parse($tsValue) : now();

        // Формируем запрос для history-logger
        // Передаём zone_id напрямую (в таблице zones нет uid)
        $sample = [
            'node_uid' => $nodeUid ?? '',
            'zone_id' => $data['zone_id'],  // Передаём zone_id напрямую
            'metric_type' => $data['metric_type'],
            'value' => $data['value'],
            'ts' => $timestamp->toIso8601String(),
            'channel' => $data['channel'] ?? null,
        ];

        // Проксируем в history-logger
        try {
            $historyLoggerUrl = Config::get('services.history_logger.url', 'http://history-logger:9300');
            $response = Http::timeout(5)->post(
                $historyLoggerUrl.'/ingest/telemetry',
                ['samples' => [$sample]]
            );

            if (! $response->successful()) {
                Log::warning('History logger request failed', [
                    'status' => $response->status(),
                    'body' => $response->body(),
                ]);

                return Response::json(['status' => 'error', 'message' => 'Failed to ingest telemetry'], 500);
            }

            return Response::json(['status' => 'ok']);
        } catch (\Exception $e) {
            Log::error('History logger request exception', [
                'message' => $e->getMessage(),
            ]);

            return Response::json(['status' => 'error', 'message' => 'Failed to ingest telemetry'], 500);
        }
    }

    public function commandAck(Request $request)
    {
        $this->ensureToken($request);
        $data = $request->validate([
            'cmd_id' => ['required', 'string', 'max:64'],
            'status' => ['required', 'string', 'in:accepted,completed,failed'],
            'details' => ['nullable', 'array'],
        ]);

        // Laravel больше не обновляет статусы команд напрямую
        // Это делает только Python-часть (history-logger через MQTT command_response)
        // Просто возвращаем подтверждение получения

        return Response::json(['status' => 'ok']);
    }
}
