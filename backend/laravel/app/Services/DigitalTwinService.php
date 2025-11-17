<?php

namespace App\Services;

use App\Models\Zone;
use App\Models\ZoneSimulation;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Log;

class DigitalTwinService
{
    /**
     * Запустить симуляцию зоны
     *
     * @param Zone $zone
     * @param array $scenario {recipe_id, initial_state: {ph, ec, temp_air, temp_water, humidity_air}}
     * @param int $durationHours
     * @param int $stepMinutes
     * @return ZoneSimulation
     */
    public function simulateZone(
        Zone $zone,
        array $scenario,
        int $durationHours = 72,
        int $stepMinutes = 10
    ): ZoneSimulation {
        $baseUrl = Config::get('services.digital_twin.base_url', 'http://digital-twin:8003');
        $token = Config::get('services.digital_twin.token');

        // Создаем запись о симуляции
        $simulation = ZoneSimulation::create([
            'zone_id' => $zone->id,
            'scenario' => $scenario,
            'duration_hours' => $durationHours,
            'step_minutes' => $stepMinutes,
            'status' => 'pending',
        ]);

        try {
            $headers = $token ? ['Authorization' => "Bearer {$token}"] : [];

            $response = Http::withHeaders($headers)
                ->timeout(300) // 5 минут на симуляцию
                ->post("{$baseUrl}/simulate/zone", [
                    'zone_id' => $zone->id,
                    'duration_hours' => $durationHours,
                    'step_minutes' => $stepMinutes,
                    'scenario' => $scenario,
                ]);

            if ($response->successful()) {
                $data = $response->json();
                $simulation->update([
                    'status' => 'completed',
                    'results' => $data['data'] ?? null,
                ]);

                Log::info('Zone simulation completed', [
                    'zone_id' => $zone->id,
                    'simulation_id' => $simulation->id,
                ]);
            } else {
                $simulation->update([
                    'status' => 'failed',
                    'error_message' => $response->body(),
                ]);

                Log::error('Zone simulation failed', [
                    'zone_id' => $zone->id,
                    'simulation_id' => $simulation->id,
                    'error' => $response->body(),
                ]);
            }
        } catch (\Exception $e) {
            $simulation->update([
                'status' => 'failed',
                'error_message' => $e->getMessage(),
            ]);

            Log::error('Zone simulation exception', [
                'zone_id' => $zone->id,
                'simulation_id' => $simulation->id,
                'error' => $e->getMessage(),
            ]);
        }

        return $simulation->fresh();
    }

    /**
     * Получить результаты симуляции
     *
     * @param int $simulationId
     * @return ZoneSimulation|null
     */
    public function getSimulation(int $simulationId): ?ZoneSimulation
    {
        return ZoneSimulation::find($simulationId);
    }
}

