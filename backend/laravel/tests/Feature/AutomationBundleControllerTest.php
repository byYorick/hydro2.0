<?php

namespace Tests\Feature;

use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AutomationBundleControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_system_bundle_is_admin_only(): void
    {
        app(AutomationConfigDocumentService::class)->ensureSystemDefaults();

        $viewer = User::factory()->create(['role' => 'viewer']);
        $admin = User::factory()->create(['role' => 'admin']);

        $this->actingAs($viewer)
            ->getJson('/api/automation-bundles/system/0')
            ->assertForbidden();

        $this->actingAs($admin)
            ->getJson('/api/automation-bundles/system/0')
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.scope_type', 'system')
            ->assertJsonPath('data.scope_id', 0);
    }

    public function test_zone_bundle_is_available_for_zone_reader(): void
    {
        app(AutomationConfigDocumentService::class)->ensureSystemDefaults();

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create([
            'greenhouse_id' => $greenhouse->id,
        ]);
        app(AutomationConfigDocumentService::class)->ensureZoneDefaults($zone->id);

        $viewer = User::factory()->create(['role' => 'viewer']);

        $this->actingAs($viewer)
            ->getJson("/api/automation-bundles/zone/{$zone->id}")
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.scope_type', 'zone')
            ->assertJsonPath('data.scope_id', $zone->id);
    }

    public function test_greenhouse_bundle_scope_is_rejected(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $operator = User::factory()->create(['role' => 'operator']);

        $this->actingAs($operator)
            ->postJson("/api/automation-bundles/greenhouse/{$greenhouse->id}/validate")
            ->assertStatus(422);
    }
}
