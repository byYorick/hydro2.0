<?php

namespace Database\Seeders;

use App\Models\SimulationEvent;
use App\Models\ZoneSimulation;
use Illuminate\Database\Seeder;

class SimulationEventSeeder extends Seeder
{
    public function run(): void
    {
        $simulation = ZoneSimulation::query()->first() ?? ZoneSimulation::factory()->create();

        SimulationEvent::factory()
            ->count(5)
            ->create([
                'simulation_id' => $simulation->id,
                'zone_id' => $simulation->zone_id,
            ]);
    }
}
