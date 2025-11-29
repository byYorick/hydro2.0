<?php

namespace App\Http\Controllers;

use App\Models\Greenhouse;
use App\Helpers\ZoneAccessHelper;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Auth;

class SystemController extends Controller
{
    public function health()
    {
        $isAuthenticated = auth()->check();
        $isAdmin = $isAuthenticated && auth()->user()->role === 'admin';
        $isDev = config('app.debug');
        
        // Для неаутентифицированных пользователей возвращаем только базовый статус
        if (!$isAuthenticated) {
            try {
                // Простая проверка БД без деталей
                DB::connection()->selectOne('SELECT 1 as test');
                return response()->json([
                    'status' => 'ok',
                    'data' => [
                        'app' => 'ok',
                        'db' => 'ok',
                    ],
                ]);
            } catch (\Throwable $e) {
                return response()->json([
                    'status' => 'fail',
                    'data' => [
                        'app' => 'fail',
                        'db' => 'fail',
                    ],
                ], 503);
            }
        }
        
        // Для аутентифицированных пользователей возвращаем детальную информацию
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
            
            // Используем Http-клиент для правильной проверки HTTP-кода
            $response = \Illuminate\Support\Facades\Http::timeout(2)
                ->get($mqttBridgeUrl . '/metrics');
            
            if ($response->successful() && $response->body()) {
                $mqttOk = 'ok';
            } else {
                $mqttOk = 'fail';
                \Log::warning('MQTT bridge health check failed', [
                    'url' => $mqttBridgeUrl . '/metrics',
                    'status' => $response->status(),
                    'has_body' => !empty($response->body()),
                ]);
            }
        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            $mqttOk = 'fail';
            \Log::warning('MQTT bridge health check: connection failed', [
                'url' => $mqttBridgeUrl ?? 'unknown',
                'error' => $e->getMessage(),
            ]);
        } catch (\Illuminate\Http\Client\TimeoutException $e) {
            $mqttOk = 'fail';
            \Log::warning('MQTT bridge health check: timeout', [
                'url' => $mqttBridgeUrl ?? 'unknown',
            ]);
        } catch (\Throwable $e) {
            // Если не удалось проверить MQTT, считаем недоступным
            $mqttOk = 'fail';
            \Log::error('MQTT bridge health check: exception', [
                'url' => $mqttBridgeUrl ?? 'unknown',
                'error' => $e->getMessage(),
            ]);
        }

        // Проверка статуса history-logger сервиса
        $historyLoggerOk = 'unknown';
        try {
            $historyLoggerUrl = env('HISTORY_LOGGER_URL', 'http://history-logger:9300');
            
            // Используем Http-клиент для правильной проверки HTTP-кода
            $response = \Illuminate\Support\Facades\Http::timeout(3)
                ->get($historyLoggerUrl . '/health');
            
            if ($response->successful()) {
                $healthData = $response->json();
                if (isset($healthData['status']) && $healthData['status'] === 'ok') {
                    $historyLoggerOk = 'ok';
                } else {
                    // Логируем проблему для отладки
                    \Log::warning('History Logger health check failed', [
                        'url' => $historyLoggerUrl . '/health',
                        'status' => $response->status(),
                        'response_status' => $healthData['status'] ?? 'unknown',
                    ]);
                    $historyLoggerOk = 'fail';
                }
            } else {
                // Логируем ошибку HTTP-кода
                \Log::warning('History Logger health check: non-successful response', [
                    'url' => $historyLoggerUrl . '/health',
                    'status' => $response->status(),
                    'body_preview' => substr($response->body(), 0, 200),
                ]);
                $historyLoggerOk = 'fail';
            }
        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            $historyLoggerOk = 'fail';
            \Log::warning('History Logger health check: connection failed', [
                'url' => $historyLoggerUrl ?? 'unknown',
                'error' => $e->getMessage(),
            ]);
        } catch (\Illuminate\Http\Client\TimeoutException $e) {
            $historyLoggerOk = 'fail';
            \Log::warning('History Logger health check: timeout', [
                'url' => $historyLoggerUrl ?? 'unknown',
            ]);
        } catch (\Throwable $e) {
            // Логируем исключение
            \Log::error('History Logger health check: exception', [
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
            
            // Используем Http-клиент для правильной проверки HTTP-кода
            $response = \Illuminate\Support\Facades\Http::timeout(2)
                ->get($automationEngineUrl . '/metrics');
            
            if ($response->successful() && $response->body()) {
                $automationEngineOk = 'ok';
            } else {
                $automationEngineOk = 'fail';
                \Log::warning('Automation engine health check failed', [
                    'url' => $automationEngineUrl . '/metrics',
                    'status' => $response->status(),
                    'has_body' => !empty($response->body()),
                ]);
            }
        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            $automationEngineOk = 'fail';
            \Log::warning('Automation engine health check: connection failed', [
                'url' => $automationEngineUrl ?? 'unknown',
                'error' => $e->getMessage(),
            ]);
        } catch (\Illuminate\Http\Client\TimeoutException $e) {
            $automationEngineOk = 'fail';
            \Log::warning('Automation engine health check: timeout', [
                'url' => $automationEngineUrl ?? 'unknown',
            ]);
        } catch (\Throwable $e) {
            $automationEngineOk = 'fail';
            \Log::error('Automation engine health check: exception', [
                'url' => $automationEngineUrl ?? 'unknown',
                'error' => $e->getMessage(),
            ]);
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
            // Добавляем метаданные для диагностики (только для админов или в dev режиме)
            ...(($isAdmin || $isDev) ? [
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
            // Проверяем авторизацию через Sanctum или сессию
            // Middleware verify.python.service уже проверил токен или Sanctum
            // Здесь просто получаем пользователя, если он авторизован
            $user = Auth::guard('sanctum')->user() ?? Auth::user();
            
            // Если пользователь не авторизован (ни через Sanctum, ни через сессию),
            // значит middleware должен был отклонить запрос, но на всякий случай проверяем
            if (!$user) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'UNAUTHENTICATED',
                    'message' => 'Authentication required',
                ], 401);
            }
            
            // Получаем доступные зоны для пользователя
            $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);
            
            // Загружаем теплицы с зонами, фильтруя по доступным зонам
            $greenhouses = Greenhouse::with([
                'zones' => function ($query) use ($accessibleZoneIds) {
                    $query->whereIn('id', $accessibleZoneIds)
                        ->select('id', 'uid', 'greenhouse_id', 'name', 'description', 'status', 'health_score', 'health_status', 'hardware_profile', 'capabilities', 'water_state', 'solution_started_at', 'settings', 'created_at', 'updated_at')
                        ->with(['nodes' => function ($nodeQuery) {
                            // Загружаем ноды без чувствительных данных конфига (Wi-Fi пароли, MQTT креды)
                            // Поле config исключаем для предотвращения утечки креденшалов
                            $nodeQuery->select('id', 'uid', 'name', 'type', 'zone_id', 'status', 'lifecycle_state', 'fw_version', 'hardware_revision', 'hardware_id', 'validated', 'first_seen_at', 'created_at', 'updated_at');
                        }, 'nodes.channels' => function ($channelQuery) {
                            // Загружаем каналы без чувствительных данных из config
                            $channelQuery->select('id', 'node_id', 'channel', 'type', 'metric', 'unit');
                            // Исключаем config из каналов для предотвращения утечки данных
                        }, 'recipeInstance.recipe']);
                },
            ])->get();
            
            // Убираем config из нод и каналов после загрузки (на случай если он был загружен через отношения)
            foreach ($greenhouses as $greenhouse) {
                foreach ($greenhouse->zones as $zone) {
                    foreach ($zone->nodes as $node) {
                        // Удаляем config для предотвращения утечки Wi-Fi паролей и MQTT кредов
                        unset($node->config);
                        
                        // Удаляем config из каналов, если он был загружен
                        foreach ($node->channels as $channel) {
                            unset($channel->config);
                        }
                    }
                }
            }
            
            // Фильтруем теплицы, оставляя только те, у которых есть доступные зоны
            // (или если пользователь админ - оставляем все)
            if (!$user->isAdmin()) {
                $greenhouses = $greenhouses->filter(function ($greenhouse) {
                    return $greenhouse->zones->isNotEmpty();
                })->values();
            }

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


