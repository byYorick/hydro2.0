<?php

namespace Tests\Unit;

use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
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
        $endDate = Carbon::now();

        for ($i = 0; $i < 2500; $i++) {
            TelemetrySample::create([
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'metric_type' => 'PH',
                'value' => 6.5 + ($i % 10) * 0.1,
                'ts' => $startDate->copy()->addHours($i / 250),
                'created_at' => $startDate->copy()->addHours($i / 250),
            ]);
        }

        for ($i = 0; $i < 2500; $i++) {
            TelemetrySample::create([
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'metric_type' => 'EC',
                'value' => 1.8 + ($i % 10) * 0.05,
                'ts' => $startDate->copy()->addHours($i / 250),
                'created_at' => $startDate->copy()->addHours($i / 250),
            ]);
        }

        $phCount = TelemetrySample::where('zone_id', $zone->id)
            ->where('metric_type', 'PH')
            ->whereBetween('ts', [$startDate, $endDate])
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
