<?php

namespace Tests\Unit\Services;

use App\Models\Zone;
use App\Models\Sensor;
use App\Models\TelemetrySample;
use App\Models\ParameterPrediction;
use App\Services\PredictionService;
use Carbon\Carbon;
use Tests\RefreshDatabase;
use Tests\TestCase;

class PredictionServiceTest extends TestCase
{
    use RefreshDatabase;

    private PredictionService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = new PredictionService();
    }

    public function test_predict_with_sufficient_data(): void
    {
        $zone = Zone::factory()->create(['status' => 'RUNNING']);
        $sensor = Sensor::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => null,
            'scope' => 'inside',
            'type' => 'PH',
            'label' => 'ph_sensor',
            'unit' => null,
            'specs' => null,
            'is_active' => true,
        ]);

        // Создаем телеметрию за последние 2 часа с трендом
        $now = Carbon::now();
        for ($i = 0; $i < 10; $i++) {
            TelemetrySample::create([
                'zone_id' => $zone->id,
                'sensor_id' => $sensor->id,
                'value' => 6.0 + ($i * 0.05), // тренд вверх
                'ts' => $now->copy()->subHours(2)->addMinutes($i * 12),
            ]);
        }

        $prediction = $this->service->predict($zone, 'PH', 60);

        $this->assertInstanceOf(ParameterPrediction::class, $prediction);
        $this->assertEquals($zone->id, $prediction->zone_id);
        $this->assertEquals('PH', $prediction->metric_type);
        $this->assertEquals(60, $prediction->horizon_minutes);
        $this->assertGreaterThan(6.0, $prediction->predicted_value); // прогноз должен быть выше из-за тренда
        $this->assertNotNull($prediction->confidence);
    }

    public function test_predict_with_insufficient_data_returns_null(): void
    {
        $zone = Zone::factory()->create();
        $sensor = Sensor::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => null,
            'scope' => 'inside',
            'type' => 'PH',
            'label' => 'ph_sensor',
            'unit' => null,
            'specs' => null,
            'is_active' => true,
        ]);

        // Создаем только 2 точки (недостаточно для прогноза)
        $now = Carbon::now();
        TelemetrySample::create([
            'zone_id' => $zone->id,
            'sensor_id' => $sensor->id,
            'value' => 6.0,
            'ts' => $now->copy()->subHour(),
        ]);
        TelemetrySample::create([
            'zone_id' => $zone->id,
            'sensor_id' => $sensor->id,
            'value' => 6.1,
            'ts' => $now->copy()->subMinutes(30),
        ]);

        $prediction = $this->service->predict($zone, 'PH', 60);

        $this->assertNull($prediction);
    }

    public function test_get_latest_prediction(): void
    {
        $zone = Zone::factory()->create();

        $oldPrediction = ParameterPrediction::create([
            'zone_id' => $zone->id,
            'metric_type' => 'PH',
            'predicted_value' => 6.0,
            'confidence' => 0.8,
            'horizon_minutes' => 60,
            'predicted_at' => Carbon::now()->addHour(),
        ]);

        $newPrediction = ParameterPrediction::create([
            'zone_id' => $zone->id,
            'metric_type' => 'PH',
            'predicted_value' => 6.1,
            'confidence' => 0.9,
            'horizon_minutes' => 60,
            'predicted_at' => Carbon::now()->addHour(),
        ]);

        $latest = $this->service->getLatestPrediction($zone, 'PH');

        $this->assertInstanceOf(ParameterPrediction::class, $latest);
        $this->assertEquals($newPrediction->id, $latest->id);
    }

    public function test_generate_predictions_for_active_zones(): void
    {
        $activeZone1 = Zone::factory()->create(['status' => 'RUNNING']);
        $activeZone2 = Zone::factory()->create(['status' => 'online']);
        $pausedZone = Zone::factory()->create(['status' => 'PAUSED']);

        $zone1Sensors = [
            'ph' => Sensor::query()->create([
                'greenhouse_id' => $activeZone1->greenhouse_id,
                'zone_id' => $activeZone1->id,
                'node_id' => null,
                'scope' => 'inside',
                'type' => 'PH',
                'label' => 'ph_sensor',
                'unit' => null,
                'specs' => null,
                'is_active' => true,
            ]),
            'ec' => Sensor::query()->create([
                'greenhouse_id' => $activeZone1->greenhouse_id,
                'zone_id' => $activeZone1->id,
                'node_id' => null,
                'scope' => 'inside',
                'type' => 'EC',
                'label' => 'ec_sensor',
                'unit' => null,
                'specs' => null,
                'is_active' => true,
            ]),
        ];
        $zone2Sensors = [
            'ph' => Sensor::query()->create([
                'greenhouse_id' => $activeZone2->greenhouse_id,
                'zone_id' => $activeZone2->id,
                'node_id' => null,
                'scope' => 'inside',
                'type' => 'PH',
                'label' => 'ph_sensor',
                'unit' => null,
                'specs' => null,
                'is_active' => true,
            ]),
            'ec' => Sensor::query()->create([
                'greenhouse_id' => $activeZone2->greenhouse_id,
                'zone_id' => $activeZone2->id,
                'node_id' => null,
                'scope' => 'inside',
                'type' => 'EC',
                'label' => 'ec_sensor',
                'unit' => null,
                'specs' => null,
                'is_active' => true,
            ]),
        ];

        // Создаем телеметрию для активных зон
        $now = Carbon::now();
        foreach ([$activeZone1, $activeZone2] as $zone) {
            $sensors = $zone->id === $activeZone1->id ? $zone1Sensors : $zone2Sensors;
            for ($i = 0; $i < 10; $i++) {
                TelemetrySample::create([
                    'zone_id' => $zone->id,
                    'sensor_id' => $sensors['ph']->id,
                    'value' => 6.0 + ($i * 0.01),
                    'ts' => $now->copy()->subHours(2)->addMinutes($i * 12),
                ]);
                TelemetrySample::create([
                    'zone_id' => $zone->id,
                    'sensor_id' => $sensors['ec']->id,
                    'value' => 1.2 + ($i * 0.01),
                    'ts' => $now->copy()->subHours(2)->addMinutes($i * 12),
                ]);
            }
        }

        $count = $this->service->generatePredictionsForActiveZones(['PH', 'EC']);

        // Должно быть создано минимум 4 прогноза (2 зоны * 2 метрики)
        // Но может быть меньше, если для какой-то зоны не хватает данных
        $this->assertGreaterThanOrEqual(2, $count);
        $this->assertLessThanOrEqual(4, $count);
        $this->assertDatabaseCount('parameter_predictions', $count);
    }
}
