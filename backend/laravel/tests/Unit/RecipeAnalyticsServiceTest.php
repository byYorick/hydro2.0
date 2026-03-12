<?php

namespace Tests\Unit;

use Tests\TestCase;
use App\Services\RecipeAnalyticsService;
use App\Models\Zone;
use App\Models\ZoneRecipeInstance;
use App\Models\Recipe;
use App\Models\TelemetrySample;
use App\Models\Alert;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Carbon\Carbon;
use Illuminate\Support\Facades\DB;

class RecipeAnalyticsServiceTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Тест расчета аналитики с chunking для предотвращения утечки памяти.
     */
    public function test_calculate_analytics_uses_chunking(): void
    {
        // Создаем зону с рецептом
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        
        $instance = ZoneRecipeInstance::create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
            'started_at' => Carbon::now()->subDays(10),
            'current_phase_index' => 0,
        ]);
        
        // Создаем фазу рецепта с целевыми значениями
        $recipe->phases()->create([
            'phase_index' => 0,
            'name' => 'Test Phase',
            'duration_hours' => 24,
            'targets' => [
                'ph' => 6.5,
                'ec' => 1.8,
            ],
        ]);
        
        // Создаем узел для телеметрии
        $node = \App\Models\DeviceNode::factory()->create(['zone_id' => $zone->id]);
        
        // Создаем большое количество телеметрии (больше чем размер чанка 1000)
        $startDate = $instance->started_at;
        $endDate = Carbon::now();
        
        // Создаем 2500 записей телеметрии PH
        for ($i = 0; $i < 2500; $i++) {
            TelemetrySample::create([
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'metric_type' => 'PH',
                'value' => 6.5 + ($i % 10) * 0.1, // Небольшие вариации
                'ts' => $startDate->copy()->addHours($i / 250),
                'created_at' => $startDate->copy()->addHours($i / 250),
            ]);
        }
        
        // Создаем 2500 записей телеметрии EC
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
        
        // Проверяем, что данные созданы
        $phCount = TelemetrySample::where('zone_id', $zone->id)
            ->where('metric_type', 'PH')
            ->whereBetween('ts', [$startDate, $endDate])
            ->count();
        $this->assertEquals(2500, $phCount);
        
        // Запускаем расчет аналитики
        $service = new RecipeAnalyticsService();
        $analytics = $service->calculateAndStore($zone->id, $instance->id);
        
        // Проверяем, что аналитика создана
        $this->assertNotNull($analytics);
        $this->assertEquals($zone->id, $analytics->zone_id);
        $this->assertEquals($recipe->id, $analytics->recipe_id);
        
        // Проверяем, что отклонения рассчитаны (не null)
        $this->assertNotNull($analytics->avg_ph_deviation);
        $this->assertNotNull($analytics->avg_ec_deviation);
    }

    /**
     * Тест расчета аналитики без телеметрии.
     */
    public function test_calculate_analytics_no_telemetry(): void
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        
        $instance = ZoneRecipeInstance::create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
            'started_at' => Carbon::now()->subDays(10),
            'current_phase_index' => 0,
        ]);
        
        $recipe->phases()->create([
            'phase_index' => 0,
            'name' => 'Test Phase',
            'duration_hours' => 24,
            'targets' => [
                'ph' => 6.5,
                'ec' => 1.8,
            ],
        ]);
        
        $service = new RecipeAnalyticsService();
        $analytics = $service->calculateAndStore($zone->id, $instance->id);
        
        $this->assertNotNull($analytics);
        // Отклонения должны быть null, так как нет телеметрии
        $this->assertNull($analytics->avg_ph_deviation);
        $this->assertNull($analytics->avg_ec_deviation);
    }

    /**
     * Тест расчета аналитики с алертами.
     */
    public function test_calculate_analytics_with_alerts(): void
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        
        $instance = ZoneRecipeInstance::create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
            'started_at' => Carbon::now()->subDays(10),
            'current_phase_index' => 0,
        ]);
        
        // Создаем несколько алертов
        for ($i = 0; $i < 5; $i++) {
            \App\Models\Alert::factory()->create([
                'zone_id' => $zone->id,
                'status' => 'active',
                'created_at' => Carbon::now()->subDays(5)->addHours($i),
            ]);
        }
        
        $service = new RecipeAnalyticsService();
        $analytics = $service->calculateAndStore($zone->id, $instance->id);
        
        $this->assertNotNull($analytics);
        $this->assertEquals(5, $analytics->alerts_count);
    }
}

