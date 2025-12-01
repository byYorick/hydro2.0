<?php

namespace App\Http\Controllers;

use App\Models\Alert;
use App\Helpers\ZoneAccessHelper;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;

class AlertStreamController extends Controller
{
    /**
     * SSE endpoint для стриминга алертов.
     * 
     * Включает проверку закрытия соединения и таймаут для предотвращения утечек PHP-FPM workers.
     * Фильтрует алерты по доступным зонам пользователя для предотвращения утечки данных.
     */
    public function stream(Request $request)
    {
        // Проверяем авторизацию
        $user = Auth::user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Получаем список доступных зон для пользователя
        $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);
        
        // Максимальное время работы стрима (30 минут)
        $maxExecutionTime = 1800;
        $startTime = time();
        
        // Таймаут для проверки соединения (2 секунды между проверками)
        $checkInterval = 2;
        
        return response()->stream(function () use ($request, $maxExecutionTime, $startTime, $checkInterval, $accessibleZoneIds) {
            $lastId = (int)($request->query('last_id', 0));
            $iterations = 0;
            
            while (true) {
                // Проверяем, не истекло ли максимальное время выполнения
                if (time() - $startTime > $maxExecutionTime) {
                    Log::info('AlertStream: Max execution time reached', [
                        'last_id' => $lastId,
                        'iterations' => $iterations,
                    ]);
                    echo "event: close\n";
                    echo "data: " . json_encode(['message' => 'Stream timeout']) . "\n\n";
                    @ob_flush();
                    @flush();
                    break;
                }
                
                // Проверяем, не закрыто ли соединение клиентом
                if (connection_aborted()) {
                    Log::debug('AlertStream: Client connection aborted', [
                        'last_id' => $lastId,
                        'iterations' => $iterations,
                    ]);
                    break;
                }
                
                // Проверяем, не превышен ли лимит памяти (опционально)
                if (memory_get_usage(true) > 128 * 1024 * 1024) { // 128 MB
                    Log::warning('AlertStream: Memory limit reached', [
                        'last_id' => $lastId,
                        'iterations' => $iterations,
                        'memory' => memory_get_usage(true),
                    ]);
                    echo "event: error\n";
                    echo "data: " . json_encode(['message' => 'Server memory limit']) . "\n\n";
                    @ob_flush();
                    @flush();
                    break;
                }
                
                try {
                    $q = Alert::query()->orderBy('id', 'asc');
                    if ($lastId > 0) {
                        $q->where('id', '>', $lastId);
                    }
                    // Фильтруем алерты по доступным зонам пользователя
                    if (!empty($accessibleZoneIds)) {
                        $q->whereIn('zone_id', $accessibleZoneIds);
                    } else {
                        // Если у пользователя нет доступа ни к одной зоне, не возвращаем алерты
                        $q->whereRaw('1 = 0');
                    }
                    $items = $q->limit(50)->get();
                    
                    foreach ($items as $a) {
                        // Проверяем соединение перед каждой отправкой
                        if (connection_aborted()) {
                            break 2; // Выходим из обоих циклов
                        }
                        
                        $lastId = max($lastId, $a->id);
                        
                        // Фильтруем данные алерта - убираем чувствительную информацию
                        $alertData = [
                            'id' => $a->id,
                            'zone_id' => $a->zone_id,
                            'type' => $a->type,
                            'status' => $a->status,
                            'severity' => $a->severity ?? null,
                            'message' => $a->message ?? null,
                            'created_at' => $a->created_at?->toIso8601String(),
                            'resolved_at' => $a->resolved_at?->toIso8601String(),
                            // Исключаем details, так как там могут быть чувствительные данные
                            // Если нужны details, их можно вернуть, но отфильтровав чувствительные поля
                        ];
                        
                        echo "event: alert\n";
                        echo "data: " . json_encode($alertData) . "\n\n";
                        @ob_flush();
                        @flush();
                    }
                } catch (\Exception $e) {
                    Log::error('AlertStream: Error during stream', [
                        'last_id' => $lastId,
                        'error' => $e->getMessage(),
                        'exception' => get_class($e),
                    ]);
                    echo "event: error\n";
                    echo "data: " . json_encode(['message' => 'Stream error occurred']) . "\n\n";
                    @ob_flush();
                    @flush();
                    break;
                }
                
                $iterations++;
                
                // Используем usleep для более точного контроля времени
                // и проверяем соединение во время ожидания
                $sleepStart = time();
                while (time() - $sleepStart < $checkInterval) {
                    if (connection_aborted()) {
                        break 2; // Выходим из обоих циклов
                    }
                    usleep(100000); // 0.1 секунды
                }
            }
        }, 200, [
            'Content-Type' => 'text/event-stream',
            'Cache-Control' => 'no-cache',
            'X-Accel-Buffering' => 'no',
            'Connection' => 'keep-alive',
        ]);
    }
}


