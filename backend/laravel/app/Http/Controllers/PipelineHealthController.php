<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class PipelineHealthController extends Controller
{
    /**
     * Health endpoint для визуализации состояния пайплайна.
     * 
     * Показывает состояние каждого компонента пайплайна:
     * - MQTT
     * - History Logger
     * - Laravel API
     * - WebSocket
     * - Database
     * - Очереди (pending_alerts, pending_status_updates)
     */
    public function pipelineHealth()
    {
        $health = [
            'status' => 'ok',
            'components' => [],
            'queues' => [],
            'latencies' => [],
        ];
        
        // Проверка БД
        $dbOk = false;
        try {
            DB::connection()->selectOne('SELECT 1 as test');
            $dbOk = true;
        } catch (\Throwable $e) {
            $health['status'] = 'degraded';
        }
        $health['components']['db'] = [
            'status' => $dbOk ? 'ok' : 'fail',
            'name' => 'Database',
        ];
        
        // Проверка MQTT через mqtt-bridge
        $mqttOk = false;
        try {
            $mqttBridgeUrl = env('MQTT_BRIDGE_URL', 'http://mqtt-bridge:9000');
            $response = Http::timeout(2)->get("{$mqttBridgeUrl}/metrics");
            $mqttOk = $response->successful();
        } catch (\Throwable $e) {
            // MQTT недоступен
        }
        $health['components']['mqtt'] = [
            'status' => $mqttOk ? 'ok' : 'fail',
            'name' => 'MQTT Bridge',
        ];
        if (!$mqttOk) {
            $health['status'] = 'degraded';
        }
        
        // Проверка History Logger
        $hlOk = false;
        $hlHealth = null;
        try {
            $historyLoggerUrl = env('HISTORY_LOGGER_URL', 'http://history-logger:9300');
            $response = Http::timeout(3)->get("{$historyLoggerUrl}/health");
            if ($response->successful()) {
                $hlHealth = $response->json();
                $hlOk = isset($hlHealth['status']) && $hlHealth['status'] === 'ok';
            }
        } catch (\Throwable $e) {
            // History Logger недоступен
        }
        $health['components']['history_logger'] = [
            'status' => $hlOk ? 'ok' : 'fail',
            'name' => 'History Logger',
            'details' => $hlHealth,
        ];
        if (!$hlOk) {
            $health['status'] = 'degraded';
        }
        
        // Проверка очередей из History Logger health
        if ($hlHealth && isset($hlHealth['components'])) {
            if (isset($hlHealth['components']['queue_alerts'])) {
                $health['queues']['alerts'] = [
                    'status' => $hlHealth['components']['queue_alerts'],
                    'name' => 'Pending Alerts',
                ];
            }
            if (isset($hlHealth['components']['queue_status_updates'])) {
                $health['queues']['status_updates'] = [
                    'status' => $hlHealth['components']['queue_status_updates'],
                    'name' => 'Pending Status Updates',
                ];
            }
        }
        
        // Проверка WebSocket (через проверку подключения Laravel Echo)
        $health['components']['websocket'] = [
            'status' => 'ok', // WebSocket проверяется на клиенте
            'name' => 'WebSocket',
            'note' => 'Checked on client side',
        ];
        
        // Laravel API всегда доступен, если запрос получен
        $health['components']['laravel_api'] = [
            'status' => 'ok',
            'name' => 'Laravel API',
        ];
        
        return response()->json($health);
    }
}
