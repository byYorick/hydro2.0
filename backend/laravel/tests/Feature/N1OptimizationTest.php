<?php

namespace Tests\Feature;

use App\Models\Alert;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\Harvest;
use App\Models\Recipe;
use App\Models\Zone;
use App\Models\ZoneRecipeInstance;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class N1OptimizationTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Проверка, что ZoneController::index использует eager loading
     */
    public function test_zone_index_uses_eager_loading(): void
    {
        $user = \App\Models\User::factory()->create();
        $greenhouse = Greenhouse::factory()->create();
        $zones = Zone::factory()->count(3)->create(['greenhouse_id' => $greenhouse->id]);

        // Подсчитываем количество запросов
        DB::enableQueryLog();
        DB::flushQueryLog();

        $response = $this->actingAs($user)->getJson('/api/zones');

        $queries = DB::getQueryLog();
        DB::disableQueryLog();

        $response->assertStatus(200);

        // Проверяем, что есть запросы для загрузки greenhouse и preset
        $queryStrings = array_column($queries, 'query');
        $hasGreenhouseQuery = false;
        $hasPresetQuery = false;

        foreach ($queryStrings as $query) {
            if (str_contains($query, 'greenhouses') && str_contains($query, 'where "id" in')) {
                $hasGreenhouseQuery = true;
            }
            if (str_contains($query, 'presets') && str_contains($query, 'where "id" in')) {
                $hasPresetQuery = true;
            }
        }

        // Если есть eager loading, должен быть один запрос для всех greenhouses
        $this->assertTrue($hasGreenhouseQuery || $hasPresetQuery, 'Eager loading should be used');
    }

    /**
     * Проверка, что ZoneController::health использует eager loading
     */
    public function test_zone_health_uses_eager_loading(): void
    {
        $user = \App\Models\User::factory()->create();
        $zone = Zone::factory()->create();
        $nodes = DeviceNode::factory()->count(2)->create(['zone_id' => $zone->id]);
        Alert::factory()->count(2)->create(['zone_id' => $zone->id, 'status' => 'ACTIVE']);

        DB::enableQueryLog();
        DB::flushQueryLog();

        $response = $this->actingAs($user)->getJson("/api/zones/{$zone->id}/health");

        $queries = DB::getQueryLog();
        DB::disableQueryLog();

        $response->assertStatus(200);

        // Проверяем, что есть запросы для загрузки nodes и alerts
        $queryStrings = array_column($queries, 'query');
        $hasNodesQuery = false;
        $hasAlertsQuery = false;

        foreach ($queryStrings as $query) {
            if (str_contains($query, 'device_nodes') && str_contains($query, 'where "zone_id" =')) {
                $hasNodesQuery = true;
            }
            if (str_contains($query, 'alerts') && str_contains($query, 'where "zone_id" =')) {
                $hasAlertsQuery = true;
            }
        }

        $this->assertTrue($hasNodesQuery, 'Nodes should be loaded with eager loading');
        $this->assertTrue($hasAlertsQuery, 'Alerts should be loaded with eager loading');
    }

    /**
     * Проверка, что NodeController::index использует eager loading
     */
    public function test_node_index_uses_eager_loading(): void
    {
        $user = \App\Models\User::factory()->create();
        $zone = Zone::factory()->create();
        $nodes = DeviceNode::factory()->count(3)->create(['zone_id' => $zone->id]);

        DB::enableQueryLog();
        DB::flushQueryLog();

        $response = $this->actingAs($user)->getJson('/api/nodes');

        $queries = DB::getQueryLog();
        DB::disableQueryLog();

        $response->assertStatus(200);

        // Проверяем, что есть запрос для загрузки zones
        $queryStrings = array_column($queries, 'query');
        $hasZoneQuery = false;

        foreach ($queryStrings as $query) {
            if (str_contains($query, 'zones') && str_contains($query, 'where "id" in')) {
                $hasZoneQuery = true;
                break;
            }
        }

        $this->assertTrue($hasZoneQuery, 'Zones should be loaded with eager loading');
    }

    /**
     * Проверка, что AlertController::index использует eager loading
     */
    public function test_alert_index_uses_eager_loading(): void
    {
        $user = \App\Models\User::factory()->create();
        $zone = Zone::factory()->create();
        $alerts = Alert::factory()->count(3)->create(['zone_id' => $zone->id]);

        DB::enableQueryLog();
        DB::flushQueryLog();

        $response = $this->actingAs($user)->getJson('/api/alerts');

        $queries = DB::getQueryLog();
        DB::disableQueryLog();

        $response->assertStatus(200);

        // Проверяем, что есть запрос для загрузки zones
        $queryStrings = array_column($queries, 'query');
        $hasZoneQuery = false;

        foreach ($queryStrings as $query) {
            if (str_contains($query, 'zones') && str_contains($query, 'where "id" in')) {
                $hasZoneQuery = true;
                break;
            }
        }

        $this->assertTrue($hasZoneQuery, 'Zones should be loaded with eager loading');
    }

    /**
     * Проверка, что ZoneService::changePhase использует eager loading
     */
    public function test_zone_service_change_phase_uses_eager_loading(): void
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        
        // Создаем фазы рецепта
        $recipe->phases()->create([
            'phase_index' => 0,
            'name' => 'Phase 0',
            'duration_days' => 7,
            'targets' => ['ph' => 6.5, 'ec' => 1.2],
        ]);
        $recipe->phases()->create([
            'phase_index' => 1,
            'name' => 'Phase 1',
            'duration_days' => 7,
            'targets' => ['ph' => 6.0, 'ec' => 1.5],
        ]);

        $instance = ZoneRecipeInstance::factory()->create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
            'current_phase_index' => 0,
        ]);

        DB::enableQueryLog();
        DB::flushQueryLog();

        $zoneService = app(\App\Services\ZoneService::class);
        $result = $zoneService->changePhase($zone, 1);

        $queries = DB::getQueryLog();
        DB::disableQueryLog();

        $this->assertEquals(1, $result->current_phase_index);

        // Проверяем, что phases загружены через eager loading
        $queryStrings = array_column($queries, 'query');
        $hasPhasesQuery = false;

        foreach ($queryStrings as $query) {
            if (str_contains($query, 'recipe_phases') && str_contains($query, 'where "recipe_id" in')) {
                $hasPhasesQuery = true;
                break;
            }
        }

        $this->assertTrue($hasPhasesQuery, 'Phases should be loaded with eager loading');
    }

    /**
     * Проверка, что ReportController::zoneHarvests использует eager loading
     */
    public function test_zone_harvests_uses_eager_loading(): void
    {
        $user = \App\Models\User::factory()->create();
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $harvests = Harvest::factory()->count(2)->create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
        ]);

        DB::enableQueryLog();
        DB::flushQueryLog();

        $response = $this->actingAs($user)->getJson("/api/reports/zones/{$zone->id}/harvests");

        $queries = DB::getQueryLog();
        DB::disableQueryLog();

        $response->assertStatus(200);

        // Проверяем, что есть запрос для загрузки recipes
        $queryStrings = array_column($queries, 'query');
        $hasRecipeQuery = false;

        foreach ($queryStrings as $query) {
            if (str_contains($query, 'recipes') && str_contains($query, 'where "id" in')) {
                $hasRecipeQuery = true;
                break;
            }
        }

        $this->assertTrue($hasRecipeQuery, 'Recipes should be loaded with eager loading');
    }
}

