<?php

namespace Tests\Feature;

use App\Models\Greenhouse;
use App\Models\InfrastructureInstance;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Foundation\Testing\DatabaseTransactions;
use Illuminate\Support\Facades\Config;
use Tests\TestCase;

class InfrastructureAccessEnforceModeTest extends TestCase
{
    use DatabaseTransactions;

    protected function setUp(): void
    {
        parent::setUp();
        Config::set('access_control.mode', 'enforce');
    }

    public function test_greenhouse_infrastructure_index_forbidden_without_assignment_in_enforce_mode(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $greenhouse = Greenhouse::factory()->create();

        InfrastructureInstance::create([
            'owner_type' => 'greenhouse',
            'owner_id' => $greenhouse->id,
            'asset_type' => 'FAN',
            'label' => 'GH Fan',
            'required' => false,
        ]);

        $response = $this->actingAs($user)->getJson("/api/greenhouses/{$greenhouse->id}/infrastructure-instances");

        $response->assertStatus(403);
        $response->assertJsonPath('status', 'error');
        $response->assertJsonPath('message', 'Forbidden: Access denied to this greenhouse');
    }

    public function test_greenhouse_infrastructure_index_allowed_with_greenhouse_assignment_in_enforce_mode(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $greenhouse = Greenhouse::factory()->create();
        $user->greenhouses()->attach($greenhouse->id);

        InfrastructureInstance::create([
            'owner_type' => 'greenhouse',
            'owner_id' => $greenhouse->id,
            'asset_type' => 'FAN',
            'label' => 'GH Fan',
            'required' => false,
        ]);

        $response = $this->actingAs($user)->getJson("/api/greenhouses/{$greenhouse->id}/infrastructure-instances");

        $response->assertOk();
        $response->assertJsonPath('status', 'ok');
        $this->assertIsArray($response->json('data'));
    }

    public function test_zone_infrastructure_index_allowed_via_greenhouse_assignment_in_enforce_mode(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $user->greenhouses()->attach($greenhouse->id);

        InfrastructureInstance::create([
            'owner_type' => 'zone',
            'owner_id' => $zone->id,
            'asset_type' => 'PUMP',
            'label' => 'Zone Pump',
            'required' => true,
        ]);

        $response = $this->actingAs($user)->getJson("/api/zones/{$zone->id}/infrastructure-instances");

        $response->assertOk();
        $response->assertJsonPath('status', 'ok');
        $this->assertIsArray($response->json('data'));
    }

    public function test_operator_cannot_create_greenhouse_infrastructure_without_assignment_in_enforce_mode(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $greenhouse = Greenhouse::factory()->create();

        $response = $this->actingAs($user)->postJson('/api/infrastructure-instances', [
            'owner_type' => 'greenhouse',
            'owner_id' => $greenhouse->id,
            'asset_type' => 'FAN',
            'label' => 'Blocked Fan',
            'required' => false,
            'specs' => [],
        ]);

        $response->assertStatus(403);
        $response->assertJsonPath('status', 'error');
        $response->assertJsonPath('message', 'Forbidden: Access denied to this greenhouse');
    }

    public function test_operator_can_create_greenhouse_infrastructure_with_assignment_in_enforce_mode(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $greenhouse = Greenhouse::factory()->create();
        $user->greenhouses()->attach($greenhouse->id);

        $response = $this->actingAs($user)->postJson('/api/infrastructure-instances', [
            'owner_type' => 'greenhouse',
            'owner_id' => $greenhouse->id,
            'asset_type' => 'FAN',
            'label' => 'Allowed Fan',
            'required' => false,
            'specs' => ['rpm' => 1200],
        ]);

        $response->assertStatus(201);
        $response->assertJsonPath('status', 'ok');
        $this->assertDatabaseHas('infrastructure_instances', [
            'owner_type' => 'greenhouse',
            'owner_id' => $greenhouse->id,
            'label' => 'Allowed Fan',
        ]);
    }
}
