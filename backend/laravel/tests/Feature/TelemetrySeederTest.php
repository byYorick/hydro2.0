<?php

namespace Tests\Feature;

use App\Models\Sensor;
use App\Models\TelemetryLast;
use App\Models\TelemetrySample;
use Database\Seeders\ExtendedGreenhousesZonesSeeder;
use Database\Seeders\ExtendedNodesChannelsSeeder;
use Database\Seeders\PresetSeeder;
use Database\Seeders\TelemetrySeeder;
use Tests\RefreshDatabase;
use Tests\TestCase;

class TelemetrySeederTest extends TestCase
{
    use RefreshDatabase;

    public function test_telemetry_seeder_creates_reduced_sample_volume(): void
    {
        $this->seed(PresetSeeder::class);
        $this->seed(ExtendedGreenhousesZonesSeeder::class);
        $this->seed(ExtendedNodesChannelsSeeder::class);
        $this->seed(TelemetrySeeder::class);

        $samplesCount = TelemetrySample::count();
        $sensorsCount = Sensor::count();
        $expectedSamplesPerSensor = 524;
        $this->assertGreaterThan(0, $samplesCount);
        $this->assertGreaterThan(0, $sensorsCount);
        $this->assertLessThanOrEqual($sensorsCount * $expectedSamplesPerSensor, $samplesCount);

        $telemetryLastCount = TelemetryLast::count();
        $this->assertGreaterThan(0, $telemetryLastCount);
        $this->assertLessThanOrEqual($sensorsCount, $telemetryLastCount);
    }
}
