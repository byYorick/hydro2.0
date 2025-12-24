<?php

namespace App\Services;

use Illuminate\Support\Facades\Redis;

class EventSequenceService
{
    /**
     * Генерирует монотонно возрастающий event_id для WebSocket событий.
     * Использует Redis INCR для генерации последовательности.
     * 
     * @return array{event_id: int, server_ts: int} event_id и server_ts в миллисекундах
     */
    public static function generateEventId(): array
    {
        $serverTs = now()->timestamp * 1000; // миллисекунды
        
        // Используем Redis для генерации монотонно возрастающего sequence
        // Ключ обновляется каждый день для предотвращения переполнения
        $dateKey = now()->format('Y-m-d');
        $sequenceKey = "ws:event_seq:{$dateKey}";
        
        try {
            // INCR возвращает новое значение после инкремента
            $sequence = Redis::incr($sequenceKey);
            
            // Устанавливаем TTL на 2 дня (на случай если события придут поздно)
            Redis::expire($sequenceKey, 2 * 24 * 60 * 60);
            
            // Комбинируем timestamp и sequence для уникальности
            // Используем timestamp в миллисекундах + sequence (последние 6 цифр)
            // Это гарантирует монотонное возрастание и уникальность
            // Максимальный sequence в день: 999999 (6 цифр)
            $eventId = (int)($serverTs * 1000000 + ($sequence % 1000000));
            
            return [
                'event_id' => $eventId,
                'server_ts' => $serverTs,
            ];
        } catch (\Exception $e) {
            // Fallback: если Redis недоступен, используем только timestamp + случайное число
            \Log::warning('EventSequenceService: Redis unavailable, using fallback', [
                'error' => $e->getMessage(),
            ]);
            
            // Генерируем event_id на основе timestamp + микросекунды
            $microseconds = (int)(microtime(true) * 1000) % 1000000;
            $eventId = (int)($serverTs + $microseconds);
            
            return [
                'event_id' => $eventId,
                'server_ts' => $serverTs,
            ];
        }
    }
}

