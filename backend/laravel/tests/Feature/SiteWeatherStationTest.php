<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\User;
use App\Services\SiteInfrastructureService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SiteWeatherStationTest extends TestCase
{
    use RefreshDatabase;

    public function test_migration_seeds_hidden_site_greenhouse_and_wx_zone(): void
    {
        $site = Greenhouse::query()->where('uid', 'site')->first();
        $this->assertNotNull($site);
        $this->assertTrue((bool) $site->is_system);

        $zone = $site->zones()->where('uid', 'wx')->first();
        $this->assertNotNull($zone);
    }

    public function test_index_hides_system_greenhouse(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        Greenhouse::factory()->create(['uid' => 'gh-user-visible', 'name' => 'Visible GH']);

        $response = $this->actingAs($admin)->getJson('/api/greenhouses');
        $response->assertOk();

        $uids = collect($response->json('data.data'))->pluck('uid')->all();
        $this->assertContains('gh-user-visible', $uids);
        $this->assertNotContains('site', $uids);
    }

    public function test_assign_and_opt_in_shared_weather_station(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $greenhouse = Greenhouse::factory()->create(['uid' => 'gh-climate-a']);
        $node = DeviceNode::factory()->create([
            'type' => 'climate',
            'zone_id' => null,
            'uid' => 'nd-wx-1',
            'name' => 'Weather A',
        ]);

        $assign = $this->actingAs($user)->postJson('/api/site/weather-stations', [
            'node_id' => $node->id,
        ]);
        $assign->assertCreated()
            ->assertJsonPath('data.id', $node->id)
            ->assertJsonPath('data.uid', 'nd-wx-1');

        $siteZoneId = app(SiteInfrastructureService::class)->ensureWeatherZone()->id;
        $this->assertDatabaseHas('nodes', [
            'id' => $node->id,
            'zone_id' => $siteZoneId,
        ]);

        $list = $this->actingAs($user)->getJson('/api/site/weather-stations');
        $list->assertOk();
        $this->assertTrue(
            collect($list->json('data'))->contains(fn ($row) => (int) $row['id'] === $node->id)
        );

        $update = $this->actingAs($user)->patchJson("/api/greenhouses/{$greenhouse->id}", [
            'shared_weather_station_node_id' => $node->id,
        ]);
        $update->assertOk()
            ->assertJsonPath('data.shared_weather_station_node_id', $node->id);

        $this->assertDatabaseHas('greenhouses', [
            'id' => $greenhouse->id,
            'shared_weather_station_node_id' => $node->id,
        ]);
    }

    public function test_two_greenhouses_can_select_same_shared_station(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $ghA = Greenhouse::factory()->create(['uid' => 'gh-a']);
        $ghB = Greenhouse::factory()->create(['uid' => 'gh-b']);
        $node = DeviceNode::factory()->create(['type' => 'climate', 'zone_id' => null]);

        app(SiteInfrastructureService::class)->assignWeatherStation($node);

        $this->actingAs($user)->patchJson("/api/greenhouses/{$ghA->id}", [
            'shared_weather_station_node_id' => $node->id,
        ])->assertOk();

        $this->actingAs($user)->patchJson("/api/greenhouses/{$ghB->id}", [
            'shared_weather_station_node_id' => $node->id,
        ])->assertOk();

        $this->assertSame($node->id, Greenhouse::query()->find($ghA->id)?->shared_weather_station_node_id);
        $this->assertSame($node->id, Greenhouse::query()->find($ghB->id)?->shared_weather_station_node_id);
    }

    public function test_cannot_opt_in_non_site_weather_node(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $greenhouse = Greenhouse::factory()->create();
        $node = DeviceNode::factory()->create(['type' => 'climate', 'zone_id' => null]);

        $this->actingAs($user)->patchJson("/api/greenhouses/{$greenhouse->id}", [
            'shared_weather_station_node_id' => $node->id,
        ])->assertStatus(422);
    }

    public function test_system_greenhouse_cannot_be_deleted(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $site = app(SiteInfrastructureService::class)->ensureSiteGreenhouse();

        $this->actingAs($admin)
            ->deleteJson("/api/greenhouses/{$site->id}")
            ->assertForbidden();
    }
}
