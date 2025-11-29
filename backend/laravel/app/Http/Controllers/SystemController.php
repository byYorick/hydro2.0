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
        $dbError = null;
        try {
            // Используем простой SELECT 1 вместо getPdo() для быстрой проверки
            DB::connection()->selectOne('SELECT 1 as test');
            $dbOk = true;
        } catch (\Throwable $e) {
            $dbOk = false;
            $dbError = $e->getMessage();
            // Логируем ошибку БД для диагностики
            \Log::error('Database health check failed', [
                'message' => $e->getMessage(),
                'code' => $e->getCode(),
                'file' => $e->getFile(),
                'line' => $e->getLine(),
            ]);
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

        // Проверка статуса history-logger сервиса
        $historyLoggerOk = 'unknown';
        try {
            $historyLoggerUrl = env('HISTORY_LOGGER_URL', 'http://history-logger:9300');
            $context = stream_context_create([
                'http' => [
                    'timeout' => 3, // Увеличено с 2 до 3 секунд
                    'ignore_errors' => true,
                ],
            ]);
            
            $healthResponse = @file_get_contents($historyLoggerUrl . '/health', false, $context);
            if ($healthResponse !== false) {
                $healthData = json_decode($healthResponse, true);
                if (isset($healthData['status']) && $healthData['status'] === 'ok') {
                    $historyLoggerOk = 'ok';
                } else {
                    // Логируем проблему для отладки
                    \Log::warning('History Logger health check failed', [
                        'url' => $historyLoggerUrl . '/health',
                        'response' => $healthResponse,
                        'parsed' => $healthData,
                    ]);
                    $historyLoggerOk = 'fail';
                }
            } else {
                // Логируем ошибку подключения
                $error = error_get_last();
                \Log::warning('History Logger health check connection failed', [
                    'url' => $historyLoggerUrl . '/health',
                    'error' => $error ? $error['message'] : 'Unknown error',
                ]);
                $historyLoggerOk = 'fail';
            }
        } catch (\Throwable $e) {
            // Логируем исключение
            \Log::error('History Logger health check exception', [
                'url' => $historyLoggerUrl ?? 'unknown',
                'exception' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
            ]);
            $historyLoggerOk = 'fail';
        }

        // Проверка статуса automation-engine сервиса (через Prometheus metrics)
        $automationEngineOk = 'unknown';
        try {
            $automationEngineUrl = env('AUTOMATION_ENGINE_URL', 'http://automation-engine:9401');
            $context = stream_context_create([
                'http' => [
                    'timeout' => 2,
                    'ignore_errors' => true,
                ],
            ]);
            
            // Проверяем доступность через /metrics endpoint
            $metrics = @file_get_contents($automationEngineUrl . '/metrics', false, $context);
            if ($metrics !== false && strlen($metrics) > 0) {
                $automationEngineOk = 'ok';
            } else {
                $automationEngineOk = 'fail';
            }
        } catch (\Throwable $e) {
            $automationEngineOk = 'fail';
        }

        // Определяем общий статус системы
        $overallStatus = 'ok';
        $hasCriticalIssues = false;
        
        // Проверяем критические компоненты
        if (!$dbOk || $mqttOk === 'fail') {
            $overallStatus = 'degraded';
            $hasCriticalIssues = true;
        }
        
        // Если есть проблемы с сервисами, статус degraded, но не fail
        if (!$hasCriticalIssues && ($historyLoggerOk === 'fail' || $automationEngineOk === 'fail')) {
            $overallStatus = 'degraded';
        }
        
        return response()->json([
            'status' => $overallStatus,
            'data' => [
                'app' => 'ok',
                'db' => $dbOk ? 'ok' : 'fail',
                'mqtt' => $mqttOk,
                'history_logger' => $historyLoggerOk,
                'automation_engine' => $automationEngineOk,
                'chain' => [
                    'db' => $dbOk ? 'ok' : 'fail',
                    'mqtt' => $mqttOk,
                    'websocket' => 'unknown', // WebSocket проверяется на клиенте
                    'ui' => 'ok', // UI всегда доступен, если запрос получен
                ],
            ],
            // Добавляем метаданные для диагностики (только в dev режиме)
            ...(config('app.debug') ? [
                'meta' => [
                    'timestamp' => now()->toIso8601String(),
                    'db_error' => $dbError,
                    'checks' => [
                        'db_timeout' => '2s',
                        'mqtt_timeout' => '2s',
                        'history_logger_timeout' => '3s',
                        'automation_engine_timeout' => '2s',
                    ],
                ],
            ] : []),
        ]);
    }

    public function configFull()
    {
        try {
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
        } catch (\Illuminate\Database\QueryException $e) {
            $isDev = app()->environment(['local', 'testing', 'development']);
            $errorMessage = $e->getMessage();
            $isMissingTable = str_contains($errorMessage, 'no such table') || 
                             str_contains($errorMessage, "doesn't exist") ||
                             str_contains($errorMessage, 'relation does not exist');
            
            \Log::error('SystemController::configFull: Database error', [
                'error' => $errorMessage,
                'is_missing_table' => $isMissingTable,
            ]);
            
            if ($isDev && $isMissingTable) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Database schema not initialized. Please run migrations.',
                    'error' => 'Missing database table',
                    'hint' => 'Run: php artisan migrate',
                    'data' => [
                        'greenhouses' => [],
                    ],
                ], 503);
            }
            
            return response()->json([
                'status' => 'error',
                'message' => 'Service temporarily unavailable. Please check database connection.',
                'data' => [
                    'greenhouses' => [],
                ],
            ], 503);
        } catch (\Exception $e) {
            \Log::error('SystemController::configFull: Error', [
                'error' => $e->getMessage(),
            ]);
            
            return response()->json([
                'status' => 'error',
                'message' => 'An error occurred while fetching configuration.',
                'data' => [
                    'greenhouses' => [],
                ],
            ], 500);
        }
    }
}


