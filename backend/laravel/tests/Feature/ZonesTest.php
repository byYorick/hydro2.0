<?php

namespace Tests\Feature;

use App\Enums\GrowCycleStatus;
use App\Models\ChannelBinding;
use App\Models\Command;
use App\Models\Greenhouse;
use App\Models\GrowCycle;
use App\Models\DeviceNode;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\GrowCycleService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZonesTest extends TestCase
{
    use RefreshDatabase;

    private function token(string $role = 'operator'): string
    {
        $user = User::factory()->create(['role' => $role]);
        $this->actingAs($user);

        return $user->createToken('test')->plainTextToken;
    }

    private function createRevisionWithPhases(Recipe $recipe, int $count = 1): RecipeRevision
    {
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        for ($index = 0; $index < $count; $index++) {
            RecipeRevisionPhase::factory()->create([
                'recipe_revision_id' => $revision->id,
                'phase_index' => $index,
                'name' => 'Phase '.($index + 1),
            ]);
        }

        return $revision;
    }

    private function createGrowCycle(Zone $zone, Recipe $recipe, Plant $plant, int $phases = 1, bool $start = false): GrowCycle
    {
        $recipe->plants()->syncWithoutDetaching([$plant->id]);
        $revision = $this->createRevisionWithPhases($recipe, $phases);
        $service = app(GrowCycleService::class);

        return $service->createCycle($zone, $revision, $plant->id, ['start_immediately' => $start]);
    }

    private function attachRequiredInfrastructure(Zone $zone): void
    {
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);

        $mainPumpChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_main',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]);

        $drainChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'drain_main',
            'type' => 'actuator',
            'metric' => 'valve',
            'unit' => null,
            'config' => [],
        ]);

        $this->bindChannelToRole($zone, $mainPumpChannel, 'main_pump', 'Основная помпа');
        $this->bindChannelToRole($zone, $drainChannel, 'drain', 'Дренаж');
    }

    private function bindChannelToRole(
        Zone $zone,
        NodeChannel $channel,
        string $role,
        string $label
    ): void {
        $instance = InfrastructureInstance::query()->firstOrCreate(
            [
                'owner_type' => 'zone',
                'owner_id' => $zone->id,
                'label' => $label,
            ],
            [
                'asset_type' => 'PUMP',
                'required' => true,
            ]
        );

        ChannelBinding::query()->updateOrCreate(
            ['node_channel_id' => $channel->id],
            [
                'infrastructure_instance_id' => $instance->id,
                'direction' => 'actuator',
                'role' => $role,
            ]
        );
    }

    public function test_zones_requires_auth(): void
    {
        $this->getJson('/api/zones')->assertStatus(401);
    }

    public function test_create_zone(): void
    {
        $token = $this->token();
        $greenhouse = Greenhouse::factory()->create();
        $resp = $this->withHeader('Authorization', 'Bearer '.$token)->postJson('/api/zones', [
            'name' => 'Zone A',
            'greenhouse_id' => $greenhouse->id,
        ]);
        $resp->assertCreated()->assertJsonPath('data.name', 'Zone A');

        $zoneId = (int) $resp->json('data.id');
        $this->assertGreaterThan(0, $zoneId);
        $this->assertDatabaseHas('automation_config_documents', [
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            'scope_type' => AutomationConfigRegistry::SCOPE_ZONE,
            'scope_id' => $zoneId,
            'source' => 'bootstrap',
        ]);
        $this->assertDatabaseHas('automation_config_versions', [
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            'scope_type' => AutomationConfigRegistry::SCOPE_ZONE,
            'scope_id' => $zoneId,
            'source' => 'bootstrap',
        ]);
    }

    public function test_create_zone_assigns_acl_and_allows_immediate_zone_access(): void
    {
        $creator = User::factory()->create(['role' => 'agronomist']);
        $viewer = User::factory()->create(['role' => 'viewer']);
        $greenhouse = Greenhouse::factory()->create();

        $response = $this->actingAs($creator)->postJson('/api/zones', [
            'name' => 'Zone ACL',
            'greenhouse_id' => $greenhouse->id,
        ]);

        $response->assertCreated();
        $zoneId = (int) $response->json('data.id');

        $this->assertDatabaseHas('user_greenhouses', [
            'user_id' => $creator->id,
            'greenhouse_id' => $greenhouse->id,
        ]);
        $this->assertDatabaseHas('user_greenhouses', [
            'user_id' => $viewer->id,
            'greenhouse_id' => $greenhouse->id,
        ]);
        $this->assertDatabaseHas('user_zones', [
            'user_id' => $creator->id,
            'zone_id' => $zoneId,
        ]);
        $this->assertDatabaseHas('user_zones', [
            'user_id' => $viewer->id,
            'zone_id' => $zoneId,
        ]);

        $this->actingAs($creator)
            ->getJson("/api/zones/{$zoneId}")
            ->assertOk()
            ->assertJsonPath('data.id', $zoneId);

        $this->actingAs($viewer)
            ->getJson("/api/zones/{$zoneId}")
            ->assertOk()
            ->assertJsonPath('data.id', $zoneId);
    }

    public function test_get_zones_list(): void
    {
        $token = $this->token();
        Zone::factory()->count(3)->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson('/api/zones');

        $resp->assertOk()
            ->assertJsonStructure(['status', 'data']);
    }

    public function test_get_zone_details(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}");

        $resp->assertOk()
            ->assertJsonPath('data.id', $zone->id)
            ->assertJsonPath('data.name', $zone->name);
    }

    public function test_update_zone(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['name' => 'Old Name']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}", ['name' => 'New Name']);

        $resp->assertOk()
            ->assertJsonPath('data.name', 'New Name');
    }

    public function test_delete_zone_without_dependencies(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->deleteJson("/api/zones/{$zone->id}");

        $resp->assertOk();
        $this->assertDatabaseMissing('zones', ['id' => $zone->id]);
    }

    public function test_delete_zone_with_active_recipe_returns_error(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $this->createGrowCycle($zone, $recipe, $plant, 1, false);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->deleteJson("/api/zones/{$zone->id}");

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cannot delete zone with active grow cycle. Please finish or abort cycle first.');
    }

    public function test_attach_recipe_to_zone(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $this->attachRequiredInfrastructure($zone);
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = $this->createRevisionWithPhases($recipe, 1);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/grow-cycles", [
                'recipe_revision_id' => $revision->id,
                'plant_id' => $plant->id,
                'start_immediately' => false,
            ]);

        $resp->assertStatus(201);
        $this->assertDatabaseHas('grow_cycles', [
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::PLANNED->value,
        ]);
    }

    public function test_change_phase(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $cycle = $this->createGrowCycle($zone, $recipe, $plant, 2, true);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/grow-cycles/{$cycle->id}/advance-phase");

        $resp->assertOk();
        $cycle->refresh();
        $this->assertEquals(1, $cycle->currentPhase->phase_index);
    }

    public function test_pause_zone(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $cycle = $this->createGrowCycle($zone, $recipe, $plant, 1, true);
        $cycle->update(['status' => GrowCycleStatus::RUNNING]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/grow-cycles/{$cycle->id}/pause");

        $resp->assertOk();
        $this->assertEquals(GrowCycleStatus::PAUSED->value, $cycle->fresh()->status->value);
    }

    public function test_resume_zone(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $cycle = $this->createGrowCycle($zone, $recipe, $plant, 1, false);
        $cycle->update(['status' => GrowCycleStatus::PAUSED]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/grow-cycles/{$cycle->id}/resume");

        $resp->assertOk();
        $this->assertEquals(GrowCycleStatus::RUNNING->value, $cycle->fresh()->status->value);
    }

    public function test_fill_zone(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/fill", [
                'target_level' => 0.9,
                'max_duration_sec' => 60,
            ]);

        $resp->assertStatus(404);
    }

    public function test_drain_zone_success(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/drain", [
                'target_level' => 0.1,
                'max_duration_sec' => 60,
            ]);

        $resp->assertStatus(404);
    }

    public function test_drain_zone_python_service_down(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/drain", [
                'target_level' => 0.1,
            ]);

        $resp->assertStatus(404);
    }

    public function test_calibrate_flow_zone_success(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-flow", [
                'node_id' => 1,
                'channel' => 'flow_sensor',
                'pump_duration_sec' => 10,
            ]);

        $resp->assertStatus(404);
    }

    public function test_calibrate_pump_zone_success(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $this->createGrowCycle($zone, $recipe, $plant, 1, false);

        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => null,
            'config' => [],
        ]);

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response([
                'status' => 'ok',
                'data' => ['command_id' => 'transport-ok'],
            ], 200),
        ]);

        $runResp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $channel->id,
                'duration_sec' => 30,
                'component' => 'npk',
            ]);

        $runResp->assertStatus(202)
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.status', 'awaiting_actual_ml');

        $runToken = (string) $runResp->json('data.run_token');
        $command = Command::query()->latest('id')->firstOrFail();
        $command->update(['status' => Command::STATUS_DONE]);

        $saveResp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $channel->id,
                'duration_sec' => 30,
                'actual_ml' => 25.5,
                'component' => 'npk',
                'skip_run' => true,
                'run_token' => $runToken,
            ]);

        $saveResp->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('message', 'Pump calibration saved')
            ->assertJsonPath('data.status', 'calibrated')
            ->assertJsonPath('data.ml_per_sec', 0.85);
    }

    public function test_calibrate_pump_zone_success_for_ph_down(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $this->createGrowCycle($zone, $recipe, $plant, 1, false);

        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_acid',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => null,
            'config' => [],
        ]);

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response([
                'status' => 'ok',
                'data' => ['command_id' => 'transport-ok'],
            ], 200),
        ]);

        $runResp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $channel->id,
                'duration_sec' => 30,
                'component' => 'ph_down',
            ]);

        $runResp->assertStatus(202)
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.status', 'awaiting_actual_ml');

        $runToken = (string) $runResp->json('data.run_token');
        $command = Command::query()->latest('id')->firstOrFail();
        $command->update(['status' => Command::STATUS_DONE]);

        $saveResp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $channel->id,
                'duration_sec' => 30,
                'actual_ml' => 15.6,
                'component' => 'ph_down',
                'skip_run' => true,
                'run_token' => $runToken,
            ]);

        $saveResp->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('message', 'Pump calibration saved')
            ->assertJsonPath('data.status', 'calibrated')
            ->assertJsonPath('data.component', 'ph_down');
    }

    public function test_calibrate_pump_rejects_one_shot_run_and_save(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => null,
            'config' => [],
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $channel->id,
                'duration_sec' => 30,
                'actual_ml' => 12.0,
                'component' => 'npk',
            ]);

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'actual_ml must be submitted in a separate save step after terminal DONE');
    }

    public function test_calibrate_pump_allows_pending_zone_channel(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);

        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_pending',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => null,
            'config' => [],
        ]);

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response([
                'status' => 'ok',
                'data' => ['success' => true, 'status' => 'awaiting_actual_ml', 'run_token' => 'pending-run-1'],
            ], 200),
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $channel->id,
                'duration_sec' => 20,
                'component' => 'npk',
            ]);

        $resp->assertStatus(202)
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('message', 'Pump calibration run accepted')
            ->assertJsonPath('data.status', 'awaiting_actual_ml');

        $this->assertIsString($resp->json('data.run_token'));
        $this->assertNotSame('', (string) $resp->json('data.run_token'));
        \Illuminate\Support\Facades\Http::assertSent(function ($request) use ($zone) {
            return str_ends_with($request->url(), "/zones/{$zone->id}/commands");
        });
        \Illuminate\Support\Facades\Http::assertNotSent(function ($request) use ($zone) {
            return str_ends_with($request->url(), "/zones/{$zone->id}/calibrate-pump");
        });
    }

    public function test_calibrate_pump_uses_system_duration_bounds(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => null,
            'config' => [],
        ]);

        app(AutomationConfigDocumentService::class)->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            [
                'ml_per_sec_min' => 0.001,
                'ml_per_sec_max' => 200,
                'min_dose_ms' => 10,
                'calibration_duration_min_sec' => 1,
                'calibration_duration_max_sec' => 300,
                'quality_score_basic' => 0.5,
                'quality_score_with_k' => 0.8,
                'quality_score_legacy' => 0.3,
                'age_warning_days' => 30,
                'age_critical_days' => 60,
                'default_run_duration_sec' => 20,
            ],
            null,
            'test'
        );

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response([
                'status' => 'ok',
                'data' => ['success' => true, 'status' => 'awaiting_actual_ml', 'run_token' => 'run-123'],
            ], 200),
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $channel->id,
                'duration_sec' => 180,
                'component' => 'npk',
            ]);

        $resp->assertStatus(202)
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('message', 'Pump calibration run accepted')
            ->assertJsonPath('data.status', 'awaiting_actual_ml');

        $this->assertIsString($resp->json('data.run_token'));
        $this->assertNotSame('', (string) $resp->json('data.run_token'));
    }

    public function test_calibrate_pump_skip_run_allows_offline_zone(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'offline']);

        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => null,
            'config' => [],
        ]);

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response([
                'status' => 'ok',
                'data' => ['success' => true, 'status' => 'saved'],
            ], 200),
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $channel->id,
                'duration_sec' => 1,
                'actual_ml' => 1.0,
                'component' => 'npk',
                'skip_run' => true,
                'manual_override' => true,
            ]);

        $resp->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('message', 'Pump calibration saved');
    }

    public function test_calibrate_pump_save_after_run_requires_run_token(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'offline']);

        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => null,
            'config' => [],
        ]);

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response([
                'status' => 'ok',
                'data' => ['success' => true, 'status' => 'awaiting_actual_ml', 'run_token' => 'run-zone-offline'],
            ], 200),
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $channel->id,
                'duration_sec' => 10,
                'actual_ml' => 5.0,
                'component' => 'npk',
                'skip_run' => true,
            ]);

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'run_token is required when saving calibration after a physical run');
    }

    public function test_calibrate_pump_save_after_run_requires_terminal_done_status(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => null,
            'config' => [],
        ]);

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response([
                'status' => 'ok',
                'data' => ['command_id' => 'transport-ok'],
            ], 200),
        ]);

        $runResp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $channel->id,
                'duration_sec' => 10,
                'component' => 'npk',
            ]);

        $runToken = (string) $runResp->json('data.run_token');
        $command = Command::query()->latest('id')->firstOrFail();
        $command->update(['status' => Command::STATUS_ACK]);

        $saveResp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $channel->id,
                'duration_sec' => 10,
                'actual_ml' => 5.0,
                'component' => 'npk',
                'skip_run' => true,
                'run_token' => $runToken,
            ]);

        $saveResp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'pump calibration run is still ACK; wait for terminal DONE before saving calibration');
    }

    public function test_calibrate_pump_save_after_failed_run_is_rejected(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => null,
            'config' => [],
        ]);

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response([
                'status' => 'ok',
                'data' => ['command_id' => 'transport-ok'],
            ], 200),
        ]);

        $runResp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $channel->id,
                'duration_sec' => 10,
                'component' => 'npk',
            ]);

        $runToken = (string) $runResp->json('data.run_token');
        $command = Command::query()->latest('id')->firstOrFail();
        $command->update(['status' => Command::STATUS_ERROR]);

        $saveResp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $channel->id,
                'duration_sec' => 10,
                'actual_ml' => 5.0,
                'component' => 'npk',
                'skip_run' => true,
                'run_token' => $runToken,
            ]);

        $saveResp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'pump calibration run ended with status ERROR; cannot save calibration');
    }

    public function test_calibrate_pump_run_allows_offline_zone_when_channel_belongs_to_zone(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'offline']);

        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => null,
            'config' => [],
        ]);

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response([
                'status' => 'ok',
                'data' => ['success' => true, 'status' => 'awaiting_actual_ml', 'run_token' => 'run-offline-zone'],
            ], 200),
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $channel->id,
                'duration_sec' => 10,
                'component' => 'npk',
            ]);

        $resp->assertStatus(202)
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('message', 'Pump calibration run accepted');
    }

    public function test_calibrate_pump_rejects_node_channel_from_other_zone(): void
    {
        $token = $this->token();

        $zone = Zone::factory()->create(['status' => 'online']);
        $otherZone = Zone::factory()->create(['status' => 'online']);

        $otherNode = DeviceNode::factory()->create([
            'zone_id' => $otherZone->id,
            'status' => 'online',
        ]);
        $foreignChannel = NodeChannel::create([
            'node_id' => $otherNode->id,
            'channel' => 'pump_a',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => null,
            'config' => [],
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/calibrate-pump", [
                'node_channel_id' => $foreignChannel->id,
                'duration_sec' => 1,
                'actual_ml' => 1.0,
                'component' => 'npk',
                'skip_run' => true,
            ]);

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'node_channel_id must belong to the selected zone');
    }

    public function test_next_phase_success(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $cycle = $this->createGrowCycle($zone, $recipe, $plant, 2, true);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/grow-cycles/{$cycle->id}/advance-phase");

        $resp->assertOk();
        $this->assertEquals(1, $cycle->fresh()->currentPhase->phase_index);
    }

    public function test_next_phase_no_current_phase(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/grow-cycles/{$cycle->id}/advance-phase");

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cycle has no current phase');
    }

    public function test_next_phase_last_phase(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $cycle = $this->createGrowCycle($zone, $recipe, $plant, 1, true);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/grow-cycles/{$cycle->id}/advance-phase");

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'No next phase available');
    }

    public function test_zone_show_includes_phase_progress(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $cycle = $this->createGrowCycle($zone, $recipe, $plant, 1, true);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}");

        $resp->assertOk()
            ->assertJsonPath('status', 'ok');

        $data = $resp->json('data');
        $this->assertArrayHasKey('active_grow_cycle', $data);
    }

    public function test_phase_progress_calculation(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $cycle = $this->createGrowCycle($zone, $recipe, $plant, 2, true);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/grow-cycle");

        $resp->assertOk();
        $this->assertNotNull($resp->json('data.cycle.progress.overall_pct'));
    }
}
