<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class DigitalTwinClient
{
    public function __construct(
        private string $baseUrl
    ) {
    }

    /**
     * Симулировать зону.
     *
     * @param int $zoneId ID зоны
     * @param array $params Параметры симуляции:
     *   - duration_hours: int (по умолчанию 72)
     *   - step_minutes: int (по умолчанию 10)
     *   - scenario: array {recipe_id, initial_state: {...}}
     * @return array Результат симуляции
     * @throws \Exception
     */
    public function simulateZone(int $zoneId, array $params): array
    {
        $url = rtrim($this->baseUrl, '/') . '/simulate/zone';
        
        $payload = [
            'zone_id' => $zoneId,
            'duration_hours' => $params['duration_hours'] ?? 72,
            'step_minutes' => $params['step_minutes'] ?? 10,
            'scenario' => $params['scenario'] ?? [],
        ];

        try {
            // Используем более короткий таймаут для синхронных запросов
            // Для длительных симуляций рекомендуется использовать очередь (RunSimulationJob)
            $response = Http::timeout(30) // 30 секунд - короткий таймаут для проверки доступности
                ->post($url, $payload);

            if ($response->successful()) {
                return $response->json();
            }

            Log::error('Digital Twin simulation failed', [
                'zone_id' => $zoneId,
                'status' => $response->status(),
                'body' => $response->body(),
            ]);

            throw new \Exception(
                "Digital Twin simulation failed: " . $response->body(),
                $response->status()
            );
        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            Log::error('Digital Twin connection error', [
                'zone_id' => $zoneId,
                'error' => $e->getMessage(),
            ]);

            throw new \Exception(
                "Failed to connect to Digital Twin service: " . $e->getMessage()
            );
        }
    }

    /**
     * Запустить live-симуляцию через digital-twin orchestrator.
     */
    public function startLiveSimulation(array $payload): array
    {
        $url = rtrim($this->baseUrl, '/') . '/simulations/live/start';

        try {
            $response = Http::timeout(30)->post($url, $payload);
            if ($response->successful()) {
                return $response->json();
            }

            Log::error('Digital Twin live simulation start failed', [
                'status' => $response->status(),
                'body' => $response->body(),
            ]);

            throw new \Exception(
                "Digital Twin live simulation start failed: " . $response->body(),
                $response->status()
            );
        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            Log::error('Digital Twin live connection error', [
                'error' => $e->getMessage(),
            ]);

            throw new \Exception(
                "Failed to connect to Digital Twin service: " . $e->getMessage()
            );
        }
    }

    /**
     * Остановить live-симуляцию через digital-twin orchestrator.
     */
    public function stopLiveSimulation(array $payload): array
    {
        $url = rtrim($this->baseUrl, '/') . '/simulations/live/stop';

        try {
            $response = Http::timeout(30)->post($url, $payload);
            if ($response->successful()) {
                return $response->json();
            }

            Log::error('Digital Twin live simulation stop failed', [
                'status' => $response->status(),
                'body' => $response->body(),
            ]);

            throw new \Exception(
                "Digital Twin live simulation stop failed: " . $response->body(),
                $response->status()
            );
        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            Log::error('Digital Twin live connection error', [
                'error' => $e->getMessage(),
            ]);

            throw new \Exception(
                "Failed to connect to Digital Twin service: " . $e->getMessage()
            );
        }
    }
}
