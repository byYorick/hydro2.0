<?php

declare(strict_types=1);

namespace App\Services\GrowCycle\Support;

/**
 * Извлекает correlation id (X-Trace-Id / X-Correlation-Id) из текущего HTTP-запроса.
 *
 * Используется для включения trace id в `zone_events.payload_json` — позволяет
 * корреляцию lifecycle событий цикла с HTTP-запросом, командами в history-logger
 * и AE3 workflow.
 */
class CorrelationIdResolver
{
    public function resolve(): ?string
    {
        if (! function_exists('request')) {
            return null;
        }

        try {
            $req = request();
            $trace = $req?->header('X-Trace-Id') ?? $req?->header('X-Correlation-Id');

            return is_string($trace) && $trace !== '' ? $trace : null;
        } catch (\Throwable) {
            return null;
        }
    }
}
