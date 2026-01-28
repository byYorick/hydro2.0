<?php

namespace Tests\Unit;

use App\Models\Zone;
use App\Services\SimulationOrchestratorService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SimulationOrchestratorServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_full_simulation_marks_zone_running_and_enables_controls(): void
    {
        $sourceZone = Zone::factory()->create([
            'status' => 'online',
            'water_state' => 'NORMAL_RECIRC',
            'capabilities' => [
                'ph_control' => false,
                'ec_control' => false,
                'climate_control' => false,
                'light_control' => false,
                'irrigation_control' => false,
            ],
        ]);

        $service = app(SimulationOrchestratorService::class);
        $context = $service->createSimulationContext($sourceZone, null, ['full_simulation' => true]);

        $simZone = $context['zone'];

        $this->assertSame('RUNNING', $simZone->status);
        $this->assertTrue($simZone->capabilities['ph_control'] ?? false);
        $this->assertTrue($simZone->capabilities['ec_control'] ?? false);
        $this->assertTrue($simZone->capabilities['climate_control'] ?? false);
        $this->assertTrue($simZone->capabilities['light_control'] ?? false);
        $this->assertTrue($simZone->capabilities['irrigation_control'] ?? false);
    }
}
