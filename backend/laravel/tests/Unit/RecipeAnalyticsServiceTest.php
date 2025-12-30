<?php

namespace Tests\Unit;

use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\Sensor;
use App\Models\TelemetrySample;
use App\Models\Zone;
use App\Services\GrowCycleService;
use App\Services\RecipeAnalyticsService;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class RecipeAnalyticsServiceTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Тест расчета аналитики с chunking для предотвращения утечки памяти.
     */
    public function test_calculate_analytics_uses_chunking(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'duration_hours' => 24,
            'ph_target' => 6.5,
            'ec_target' => 1.8,
        ]);

        $service = app(GrowCycleService::class);
        $cycle = $service->createCycle($zone, $revision, $plant->id, ['start_immediately' => true]);

        $startDate = Carbon::now()->subDays(10);
        $cycle->update([
            'started_at' => $startDate,
            'planting_at' => $startDate,
        ]);

        $node = \App\Models\DeviceNode::factory()->create(['zone_id' => $zone->id]);
        $phSensor = Sensor::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'scope' => 'inside',
            'type' => 'PH',
            'label' => 'ph_sensor',
            'unit' => null,
            'specs' => null,
            'is_active' => true,
        ]);
        $ecSensor = Sensor::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'scope' => 'inside',
            'type' => 'EC',
            'label' => 'ec_sensor',
            'unit' => null,
            'specs' => null,
            'is_active' => true,
        ]);
        $endDate = Carbon::now();

        for ($i = 0; $i < 2500; $i++) {
            TelemetrySample::create([
                'zone_id' => $zone->id,
                'sensor_id' => $phSensor->id,
                'value' => 6.5 + ($i % 10) * 0.1,
                'ts' => $startDate->copy()->addHours($i / 250),
                'created_at' => $startDate->copy()->addHours($i / 250),
            ]);
        }

        for ($i = 0; $i < 2500; $i++) {
            TelemetrySample::create([
                'zone_id' => $zone->id,
                'sensor_id' => $ecSensor->id,
                'value' => 1.8 + ($i % 10) * 0.05,
                'ts' => $startDate->copy()->addHours($i / 250),
                'created_at' => $startDate->copy()->addHours($i / 250),
            ]);
        }

        $phCount = TelemetrySample::where('telemetry_samples.zone_id', $zone->id)
            ->join('sensors', 'telemetry_samples.sensor_id', '=', 'sensors.id')
            ->where('sensors.type', 'PH')
            ->whereBetween('telemetry_samples.ts', [$startDate, $endDate])
            ->count();
        $this->assertEquals(2500, $phCount);

        $analyticsService = new RecipeAnalyticsService;
        $analytics = $analyticsService->calculateAndStore($zone->id, $cycle->id);

        $this->assertNotNull($analytics);
        $this->assertEquals($zone->id, $analytics->zone_id);
        $this->assertEquals($recipe->id, $analytics->recipe_id);
        $this->assertNotNull($analytics->avg_ph_deviation);
        $this->assertNotNull($analytics->avg_ec_deviation);
    }

    /**
     * Тест расчета аналитики без телеметрии.
     */
    public function test_calculate_analytics_no_telemetry(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'duration_hours' => 24,
            'ph_target' => 6.5,
            'ec_target' => 1.8,
        ]);

        $service = app(GrowCycleService::class);
        $cycle = $service->createCycle($zone, $revision, $plant->id, ['start_immediately' => true]);

        $analyticsService = new RecipeAnalyticsService;
        $analytics = $analyticsService->calculateAndStore($zone->id, $cycle->id);

        $this->assertNotNull($analytics);
        $this->assertNull($analytics->avg_ph_deviation);
        $this->assertNull($analytics->avg_ec_deviation);
    }

    /**
     * Тест расчета аналитики с алертами.
     */
    public function test_calculate_analytics_with_alerts(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'duration_hours' => 24,
        ]);

        $service = app(GrowCycleService::class);
        $cycle = $service->createCycle($zone, $revision, $plant->id, ['start_immediately' => true]);
        $cycle->update([
            'started_at' => Carbon::now()->subDays(10),
            'planting_at' => Carbon::now()->subDays(10),
        ]);

        for ($i = 0; $i < 5; $i++) {
            \App\Models\Alert::factory()->create([
                'zone_id' => $zone->id,
                'status' => 'active',
                'created_at' => Carbon::now()->subDays(5)->addHours($i),
            ]);
        }

        $analyticsService = new RecipeAnalyticsService;
        $analytics = $analyticsService->calculateAndStore($zone->id, $cycle->id);

        $this->assertNotNull($analytics);
        $this->assertEquals(5, $analytics->alerts_count);
    }
}
