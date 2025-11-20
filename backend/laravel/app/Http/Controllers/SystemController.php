<?php

namespace App\Http\Controllers;

use App\Models\Greenhouse;
use Illuminate\Support\Facades\DB;

class SystemController extends Controller
{
    public function health()
    {
        // Быстрая проверка подключения к БД с таймаутом
        $dbOk = false;
        try {
            // Используем простой SELECT 1 вместо getPdo() для быстрой проверки
            DB::connection()->selectOne('SELECT 1 as test');
            $dbOk = true;
        } catch (\Throwable $e) {
            $dbOk = false;
        }

        // Проверка статуса MQTT через mqtt-bridge сервис
        $mqttOk = 'unknown';
        try {
            // Проверяем доступность mqtt-bridge сервиса через метрики
            // В dev окружении он доступен на mqtt-bridge:9000, в prod может быть другой адрес
            $mqttBridgeUrl = env('MQTT_BRIDGE_URL', 'http://mqtt-bridge:9000');
            $context = stream_context_create([
                'http' => [
                    'timeout' => 2, // Таймаут 2 секунды
                    'ignore_errors' => true,
                ],
            ]);
            
            // Проверяем доступность через /metrics endpoint
            $metrics = @file_get_contents($mqttBridgeUrl . '/metrics', false, $context);
            if ($metrics !== false && strlen($metrics) > 0) {
                $mqttOk = 'ok';
            } else {
                $mqttOk = 'fail';
            }
        } catch (\Throwable $e) {
            // Если не удалось проверить MQTT, считаем недоступным
            $mqttOk = 'fail';
        }

        return response()->json([
            'status' => 'ok',
            'data' => [
                'app' => 'ok',
                'db' => $dbOk ? 'ok' : 'fail',
                'mqtt' => $mqttOk,
            ],
        ]);
    }

    public function configFull()
    {
        $greenhouses = Greenhouse::with([
            'zones.nodes.channels',
            'zones.recipeInstance.recipe',
        ])->get();

        return response()->json([
            'status' => 'ok',
            'data' => [
                'greenhouses' => $greenhouses,
            ],
        ]);
    }
}


