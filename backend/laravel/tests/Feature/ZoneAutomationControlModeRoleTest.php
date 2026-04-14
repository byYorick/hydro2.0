<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

/**
 * Контроль role-based перехода между control_mode.
 * См. doc_ai/06_DOMAIN_ZONES_RECIPES/CONTROL_MODES_SPEC.md §8.1.
 */
class ZoneAutomationControlModeRoleTest extends TestCase
{
    use RefreshDatabase;

    public function test_viewer_cannot_change_control_mode(): void
    {
        $zone = Zone::factory()->create(['control_mode' => 'auto']);
        $viewer = User::factory()->create(['role' => 'viewer']);

        // Viewer не пройдёт через ZoneAccessHelper в большинстве случаев,
        // но если канал доступа открыт через zone access policy — role guard всё равно блокирует.
        $response = $this->actingAs($viewer)
            ->postJson("/api/zones/{$zone->id}/control-mode", [
                'control_mode' => 'manual',
            ]);

        $response->assertStatus(403);
    }

    public function test_operator_can_switch_to_manual_for_emergency_with_reason(): void
    {
        $zone = Zone::factory()->create(['control_mode' => 'auto']);
        $operator = User::factory()->create(['role' => 'operator']);

        Http::fake([
            '*/zones/*/control-mode' => Http::response(['status' => 'ok', 'data' => ['control_mode' => 'manual']], 200),
        ]);

        $response = $this->actingAs($operator)
            ->postJson("/api/zones/{$zone->id}/control-mode", [
                'control_mode' => 'manual',
                'reason' => 'emergency stop по сигналу',
            ]);

        $response->assertStatus(200);
    }

    public function test_operator_must_provide_reason_for_emergency_manual(): void
    {
        $zone = Zone::factory()->create(['control_mode' => 'auto']);
        $operator = User::factory()->create(['role' => 'operator']);

        $response = $this->actingAs($operator)
            ->postJson("/api/zones/{$zone->id}/control-mode", [
                'control_mode' => 'manual',
            ]);

        $response->assertStatus(422);
        $response->assertJsonPath('code', 'REASON_REQUIRED_FOR_OPERATOR_EMERGENCY');
    }

    public function test_operator_cannot_switch_back_from_manual(): void
    {
        $zone = Zone::factory()->create(['control_mode' => 'manual']);
        $operator = User::factory()->create(['role' => 'operator']);

        $response = $this->actingAs($operator)
            ->postJson("/api/zones/{$zone->id}/control-mode", [
                'control_mode' => 'auto',
                'reason' => 'restore',
            ]);

        $response->assertStatus(403);
        $response->assertJsonPath('code', 'CONTROL_MODE_FORBIDDEN_FOR_ROLE');
    }

    public function test_agronomist_can_switch_in_any_direction(): void
    {
        $zone = Zone::factory()->create(['control_mode' => 'manual']);
        $agronomist = User::factory()->create(['role' => 'agronomist']);

        Http::fake([
            '*/zones/*/control-mode' => Http::response(['status' => 'ok', 'data' => ['control_mode' => 'auto']], 200),
        ]);

        $response = $this->actingAs($agronomist)
            ->postJson("/api/zones/{$zone->id}/control-mode", [
                'control_mode' => 'auto',
            ]);

        $response->assertStatus(200);
    }
}
