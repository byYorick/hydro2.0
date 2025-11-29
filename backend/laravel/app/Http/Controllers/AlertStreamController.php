<?php

namespace App\Http\Controllers;

use App\Models\Alert;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

class AlertStreamController extends Controller
{
    /**
     * SSE endpoint для стриминга алертов.
     * 
     * Включает проверку закрытия соединения и таймаут для предотвращения утечек PHP-FPM workers.
     */
    public function stream(Request $request)
    {
        // Максимальное время работы стрима (30 минут)
        $maxExecutionTime = 1800;
        $startTime = time();
        
        // Таймаут для проверки соединения (2 секунды между проверками)
        $checkInterval = 2;
        
        return response()->stream(function () use ($request, $maxExecutionTime, $startTime, $checkInterval) {
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
                    $items = $q->limit(50)->get();
                    
                    foreach ($items as $a) {
                        // Проверяем соединение перед каждой отправкой
                        if (connection_aborted()) {
                            break 2; // Выходим из обоих циклов
                        }
                        
                        $lastId = max($lastId, $a->id);
                        echo "event: alert\n";
                        echo "data: " . json_encode($a) . "\n\n";
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


