<?php

namespace App\Http\Controllers;

use App\Models\Command;
use App\Models\Zone;
use App\Models\DeviceNode;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Response;
use Illuminate\Support\Facades\Log;

class PythonIngestController extends Controller
{
    private function ensureToken(Request $request): void
    {
        $expected = Config::get('services.python_bridge.ingest_token') ?? Config::get('services.python_bridge.token');
        $given = $request->bearerToken();
        abort_unless($expected && hash_equals($expected, (string)$given), 401);
    }

    public function telemetry(Request $request)
    {
        $this->ensureToken($request);
        $data = $request->validate([
            'zone_id' => ['required','integer'],
            'node_id' => ['nullable','integer'],
            'metric_type' => ['required','string','max:64'],
            'value' => ['required','numeric'],
            'ts' => ['nullable','date'],
            'channel' => ['nullable','string','max:64'],
        ]);
        
        // Получаем node_uid из БД
        $nodeUid = null;
        if ($data['node_id']) {
            $node = DeviceNode::find($data['node_id']);
            if ($node) {
                $nodeUid = $node->uid;
            }
        }
        
        // Формируем запрос для history-logger
        // Передаём zone_id напрямую (в таблице zones нет uid)
        $sample = [
            'node_uid' => $nodeUid ?? '',
            'zone_id' => $data['zone_id'],  // Передаём zone_id напрямую
            'metric_type' => $data['metric_type'],
            'value' => $data['value'],
            'ts' => $data['ts'] ? $data['ts']->toIso8601String() : now()->toIso8601String(),
            'channel' => $data['channel'] ?? null,
        ];
        
        // Проксируем в history-logger
        try {
            $historyLoggerUrl = Config::get('services.history_logger.url', 'http://history-logger:9300');
            $response = Http::timeout(5)->post(
                $historyLoggerUrl . '/ingest/telemetry',
                ['samples' => [$sample]]
            );
            
            if (!$response->successful()) {
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
            'cmd_id' => ['required','string','max:64'],
            'status' => ['required','string','in:accepted,completed,failed'],
            'details' => ['nullable','array'],
        ]);
        
        // Laravel больше не обновляет статусы команд напрямую
        // Это делает только Python-часть (history-logger через MQTT command_response)
        // Просто возвращаем подтверждение получения
        
        return Response::json(['status' => 'ok']);
    }
}

