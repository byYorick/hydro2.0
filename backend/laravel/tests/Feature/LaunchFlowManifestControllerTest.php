<?php

namespace Tests\Feature;

use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Tests\RefreshDatabase;
use Tests\TestCase;

class LaunchFlowManifestControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_manifest_requires_authentication(): void
    {
        $this->getJson('/api/launch-flow/manifest')
            ->assertUnauthorized();
    }

    public function test_manifest_returns_steps_without_zone(): void
    {
        $user = User::factory()->create(['role' => 'admin']);

        $response = $this->actingAs($user)
            ->getJson('/api/launch-flow/manifest')
            ->assertOk()
            ->assertJsonPath('status', 'ok');

        $steps = $response->json('data.steps');
        $this->assertIsArray($steps);
        $this->assertNotEmpty($steps);
        $ids = array_column($steps, 'id');
        $this->assertContains('zone', $ids);
        $this->assertContains('recipe', $ids);
        $this->assertContains('preview', $ids);
    }

    public function test_manifest_hides_zone_step_when_zone_provided(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $user = User::factory()->create(['role' => 'admin']);

        $response = $this->actingAs($user)
            ->getJson("/api/launch-flow/manifest?zone_id={$zone->id}")
            ->assertOk();

        $steps = collect($response->json('data.steps'))->keyBy('id');
        $this->assertFalse($steps['zone']['visible']);
        $this->assertTrue($steps['recipe']['visible']);
        $this->assertTrue($steps['preview']['visible']);
    }

    public function test_manifest_returns_readiness_block(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $user = User::factory()->create(['role' => 'admin']);

        $response = $this->actingAs($user)
            ->getJson("/api/launch-flow/manifest?zone_id={$zone->id}")
            ->assertOk();

        $response->assertJsonStructure([
            'data' => [
                'zone_id',
                'role',
                'steps',
                'role_hints',
                'readiness' => ['ready', 'blockers', 'warnings'],
            ],
        ]);
    }

    public function test_manifest_returns_role(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);

        $this->actingAs($user)
            ->getJson('/api/launch-flow/manifest')
            ->assertOk()
            ->assertJsonPath('data.role', 'agronomist');
    }

    public function test_manifest_returns_role_hints_map(): void
    {
        $user = User::factory()->create(['role' => 'admin']);

        $response = $this->actingAs($user)
            ->getJson('/api/launch-flow/manifest')
            ->assertOk();

        $hints = $response->json('data.role_hints');
        $this->assertIsArray($hints);
        $this->assertArrayHasKey('operator', $hints);
        $this->assertArrayHasKey('agronomist', $hints);
        $this->assertArrayHasKey('engineer', $hints);
    }

    public function test_manifest_rejects_invalid_zone_id(): void
    {
        $user = User::factory()->create(['role' => 'admin']);

        $this->actingAs($user)
            ->getJson('/api/launch-flow/manifest?zone_id=abc')
            ->assertStatus(422)
            ->assertJsonPath('error.code', 'invalid_zone_id');
    }

    public function test_manifest_returns_404_for_missing_zone(): void
    {
        $user = User::factory()->create(['role' => 'admin']);

        $this->actingAs($user)
            ->getJson('/api/launch-flow/manifest?zone_id=9999999')
            ->assertNotFound()
            ->assertJsonPath('error.code', 'zone_not_found');
    }

    public function test_calibration_step_visible_when_zone_selected(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $user = User::factory()->create(['role' => 'admin']);

        $response = $this->actingAs($user)
            ->getJson("/api/launch-flow/manifest?zone_id={$zone->id}")
            ->assertOk();

        $steps = collect($response->json('data.steps'))->keyBy('id');

        $this->assertTrue((bool) $steps['calibration']['visible']);
    }

    public function test_viewer_can_request_manifest(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);

        $this->actingAs($user)
            ->getJson('/api/launch-flow/manifest')
            ->assertOk();
    }

    public function test_each_step_has_required_keys(): void
    {
        $user = User::factory()->create(['role' => 'admin']);

        $response = $this->actingAs($user)
            ->getJson('/api/launch-flow/manifest')
            ->assertOk();

        foreach ($response->json('data.steps') as $step) {
            $this->assertArrayHasKey('id', $step);
            $this->assertArrayHasKey('title', $step);
            $this->assertArrayHasKey('visible', $step);
            $this->assertArrayHasKey('required', $step);
        }
    }
}
