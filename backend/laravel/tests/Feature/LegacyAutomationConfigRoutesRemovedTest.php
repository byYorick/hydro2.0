<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Models\Greenhouse;
use Tests\RefreshDatabase;
use Tests\TestCase;

class LegacyAutomationConfigRoutesRemovedTest extends TestCase
{
    use RefreshDatabase;

    public function test_zone_legacy_automation_routes_are_not_registered(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'operator']);

        $this->actingAs($user)
            ->getJson("/api/zones/{$zone->id}/automation-logic-profile")
            ->assertNotFound();

        $this->actingAs($user)
            ->postJson("/api/zones/{$zone->id}/automation-logic-profile", [
                'mode' => 'setup',
                'activate' => true,
                'subsystems' => [],
            ])
            ->assertNotFound();

        $this->actingAs($user)
            ->getJson("/api/zones/{$zone->id}/process-calibrations")
            ->assertNotFound();

        $this->actingAs($user)
            ->getJson("/api/zones/{$zone->id}/process-calibrations/generic")
            ->assertNotFound();

        $this->actingAs($user)
            ->putJson("/api/zones/{$zone->id}/process-calibrations/generic", [
                'source' => 'manual',
                'gains' => ['system_gain_ml' => 1.0],
            ])
            ->assertNotFound();

        $this->actingAs($user)
            ->getJson("/api/zones/{$zone->id}/correction-config")
            ->assertNotFound();

        $this->actingAs($user)
            ->putJson("/api/zones/{$zone->id}/correction-config", [
                'preset_id' => null,
                'base_config' => [],
                'phase_overrides' => [],
            ])
            ->assertNotFound();

        $this->actingAs($user)
            ->getJson("/api/zones/{$zone->id}/pid-configs/ph")
            ->assertNotFound();

        $this->actingAs($user)
            ->putJson("/api/zones/{$zone->id}/pid-configs/ph", [
                'target' => 5.8,
                'dead_zone' => 0.05,
            ])
            ->assertNotFound();
    }

    public function test_system_legacy_automation_settings_routes_are_not_registered(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);

        $this->actingAs($admin)
            ->getJson('/api/system/automation-settings')
            ->assertNotFound();

        $this->actingAs($admin)
            ->getJson('/api/system/automation-settings/automation_defaults')
            ->assertNotFound();

        $this->actingAs($admin)
            ->putJson('/api/system/automation-settings/automation_defaults', [
                'lighting_enabled' => true,
            ])
            ->assertNotFound();

        $this->actingAs($admin)
            ->postJson('/api/system/automation-settings/automation_defaults/reset')
            ->assertNotFound();

        $this->actingAs($admin)
            ->getJson('/api/correction-config-presets')
            ->assertNotFound();

        $this->actingAs($admin)
            ->postJson('/api/correction-config-presets', [
                'name' => 'legacy',
                'config' => [],
            ])
            ->assertNotFound();
    }

    public function test_greenhouse_legacy_automation_routes_are_not_registered(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $user = User::factory()->create(['role' => 'operator']);

        $this->actingAs($user)
            ->getJson("/api/greenhouses/{$greenhouse->id}/automation-logic-profile")
            ->assertNotFound();

        $this->actingAs($user)
            ->postJson("/api/greenhouses/{$greenhouse->id}/automation-logic-profile", [
                'mode' => 'setup',
                'activate' => true,
                'subsystems' => [
                    'climate' => [
                        'enabled' => true,
                        'execution' => [],
                    ],
                ],
            ])
            ->assertNotFound();
    }
}
