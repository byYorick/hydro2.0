<?php

namespace Tests\Feature;

use App\Enums\GrowCycleStatus;
use App\Models\Alert;
use App\Models\AutomationConfigDocument;
use App\Models\ChannelBinding;
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
use App\Services\ZoneLogicProfileCatalog;
use App\Services\ZoneLogicProfileService;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

class GrowCycleControllerTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    private Zone $zone;

    private Plant $plant;

    private Recipe $recipe;

    private RecipeRevision $revision;

    protected function setUp(): void
    {
        parent::setUp();
        config()->set('services.automation_engine.grow_cycle_start_dispatch_enabled', true);
        $this->user = User::factory()->create(['role' => 'agronomist']);
        $this->zone = Zone::factory()->create();
        $this->plant = Plant::factory()->create();
        $this->recipe = Recipe::factory()->create();
        $this->revision = RecipeRevision::factory()->create([
            'recipe_id' => $this->recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $this->revision->id,
            'phase_index' => 0,
        ]);

        $this->attachRequiredInfrastructure($this->zone);
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

    private function createPumpCalibration(NodeChannel $channel, string $component, float $mlPerSec): void
    {
        DB::table('pump_calibrations')->insert([
            'node_channel_id' => $channel->id,
            'component' => $component,
            'ml_per_sec' => $mlPerSec,
            'source' => 'test_fixture',
            'sample_count' => 1,
            'valid_from' => now(),
            'is_active' => true,
            'created_at' => now(),
            'updated_at' => now(),
        ]);
    }

    private function createPidConfigs(Zone $zone): void
    {
        $documents = app(AutomationConfigDocumentService::class);
        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            [
                'dead_zone' => 0.05,
                'close_zone' => 0.3,
                'far_zone' => 1.0,
                'zone_coeffs' => [
                    'close' => ['kp' => 5.0, 'ki' => 0.05, 'kd' => 0.0],
                    'far' => ['kp' => 8.0, 'ki' => 0.02, 'kd' => 0.0],
                ],
                'max_integral' => 20.0,
            ]
        );
        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_PID_EC,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            [
                'dead_zone' => 0.1,
                'close_zone' => 0.5,
                'far_zone' => 1.5,
                'zone_coeffs' => [
                    'close' => ['kp' => 30.0, 'ki' => 0.3, 'kd' => 0.0],
                    'far' => ['kp' => 50.0, 'ki' => 0.1, 'kd' => 0.0],
                ],
                'max_integral' => 100.0,
            ]
        );
    }

    /**
     * @param  array<string, mixed>  $subsystems
     */
    private function saveZoneLogicProfile(Zone $zone, array $subsystems): void
    {
        app(ZoneLogicProfileService::class)->upsertProfile(
            zone: $zone,
            mode: ZoneLogicProfileCatalog::MODE_SETUP,
            subsystems: $subsystems,
            activate: true,
            userId: null,
        );
    }

    private function pidAuthorityDocumentCount(Zone $zone): int
    {
        return AutomationConfigDocument::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->whereIn('namespace', [
                AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH,
                AutomationConfigRegistry::NAMESPACE_ZONE_PID_EC,
            ])
            ->count();
    }

    #[Test]
    public function it_creates_a_grow_cycle(): void
    {
        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => false,
            ]);

        $response->assertStatus(201)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'id',
                    'zone_id',
                    'recipe_revision_id',
                    'status',
                ],
            ]);

        $this->assertDatabaseHas('grow_cycles', [
            'zone_id' => $this->zone->id,
            'recipe_revision_id' => $this->revision->id,
            'status' => GrowCycleStatus::PLANNED->value,
        ]);
    }

    #[Test]
    public function it_creates_and_starts_cycle_immediately(): void
    {
        $this->createPidConfigs($this->zone);

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => true,
            ]);

        $response->assertStatus(201);

        $cycle = GrowCycle::where('zone_id', $this->zone->id)->first();
        $this->assertEquals(GrowCycleStatus::RUNNING, $cycle->status);
        $this->assertNotNull($cycle->planting_at);
        $this->assertSame('RUNNING', $this->zone->fresh()->status);
    }

    #[Test]
    public function it_rejects_start_endpoint_when_zone_is_not_ready(): void
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'recipe_revision_id' => $this->revision->id,
            'plant_id' => $this->plant->id,
            'status' => GrowCycleStatus::PLANNED,
        ]);
        $initialZoneStatus = (string) $this->zone->fresh()->status;

        AutomationConfigDocument::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $this->zone->id)
            ->whereIn('namespace', [
                AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH,
                AutomationConfigRegistry::NAMESPACE_ZONE_PID_EC,
            ])
            ->delete();

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/start");

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Zone is not ready for cycle start')
            ->assertJsonPath('readiness.checks.pid_config_ph', false)
            ->assertJsonPath('readiness.checks.pid_config_ec', false);

        $cycle->refresh();
        $this->assertSame(GrowCycleStatus::PLANNED, $cycle->status);
        $this->assertSame($initialZoneStatus, (string) $this->zone->fresh()->status);
    }

    #[Test]
    public function it_rejects_immediate_start_when_required_zone_pid_authority_documents_are_not_saved(): void
    {
        $this->assertSame(0, $this->pidAuthorityDocumentCount($this->zone));

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => true,
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Zone is not ready for cycle start')
            ->assertJsonPath('readiness.checks.pid_config_ph', false)
            ->assertJsonPath('readiness.checks.pid_config_ec', false);

        $errors = $response->json('readiness_errors', []);
        $this->assertContains('PID-настройки pH не сохранены для зоны', $errors);
        $this->assertContains('PID-настройки EC не сохранены для зоны', $errors);
        $this->assertSame(0, $this->pidAuthorityDocumentCount($this->zone));
    }

    #[Test]
    public function it_saves_irrigation_start_parameters_in_cycle_settings(): void
    {
        $this->createPidConfigs($this->zone);

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => true,
                'irrigation' => [
                    'system_type' => 'nft',
                    'interval_minutes' => 20,
                    'duration_seconds' => 20,
                    'clean_tank_fill_l' => 300,
                    'nutrient_tank_target_l' => 280,
                    'irrigation_batch_l' => 2.5,
                ],
            ]);

        $response->assertStatus(201);

        $cycle = GrowCycle::query()
            ->where('zone_id', $this->zone->id)
            ->latest('id')
            ->first();

        $this->assertNotNull($cycle);
        $this->assertSame('nft', data_get($cycle->settings, 'irrigation.system_type'));
        $this->assertSame(20, data_get($cycle->settings, 'irrigation.interval_minutes'));
        $this->assertSame(20, data_get($cycle->settings, 'irrigation.duration_seconds'));
        $this->assertSame(300, data_get($cycle->settings, 'irrigation.clean_tank_fill_l'));
        $this->assertSame(280, data_get($cycle->settings, 'irrigation.nutrient_tank_target_l'));
        $this->assertSame(2.5, data_get($cycle->settings, 'irrigation.irrigation_batch_l'));
    }

    #[Test]
    public function it_rejects_phase_overrides_for_recipe_phase_targets(): void
    {
        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => false,
                'phase_overrides' => [
                    'ph_target' => 6.0,
                ],
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonValidationErrors(['phase_overrides']);
    }

    #[Test]
    public function it_blocks_cycle_start_when_zone_has_no_bound_nodes(): void
    {
        $zoneWithoutNodes = Zone::factory()->create();

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$zoneWithoutNodes->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => true,
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Zone is not ready for cycle start')
            ->assertJsonPath('readiness.nodes.total', 0);

        $errors = $response->json('readiness_errors', []);
        $this->assertContains('Нет привязанных нод в зоне', $errors);
        $this->assertContains('Основная помпа не привязана к каналу', $errors);
        // Для AE3 после bootstrap активен two-tank профиль — дренаж не входит в обязательные роли.
        $this->assertNotContains('Дренаж не привязан к каналу', $errors);
        $this->assertNotContains('Нет онлайн нод в зоне', $errors);
        $this->assertNotContains('Zone has no bound nodes', $errors);
        $this->assertNotContains('Required bindings are missing: main_pump, drain', $errors);
    }

    #[Test]
    public function it_allows_creating_planned_cycle_when_zone_is_not_ready(): void
    {
        $zoneWithoutNodes = Zone::factory()->create();

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$zoneWithoutNodes->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => false,
            ]);

        $response->assertStatus(201)
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.status', GrowCycleStatus::PLANNED->value);

        $this->assertDatabaseHas('grow_cycles', [
            'zone_id' => $zoneWithoutNodes->id,
            'recipe_revision_id' => $this->revision->id,
            'plant_id' => $this->plant->id,
            'status' => GrowCycleStatus::PLANNED->value,
        ]);
    }

    #[Test]
    public function it_blocks_cycle_start_when_ec_control_is_enabled_but_ec_pumps_are_missing(): void
    {
        $ecZone = Zone::factory()->create([
            'capabilities' => [
                'ec_control' => true,
                'ph_control' => false,
            ],
        ]);
        $this->attachRequiredInfrastructure($ecZone);

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$ecZone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => true,
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Zone is not ready for cycle start');

        $errors = $response->json('readiness_errors', []);
        $this->assertContains('Насос EC NPK не привязан к каналу', $errors);
        $this->assertContains('Насос EC Calcium не привязан к каналу', $errors);
        $this->assertContains('Насос EC Magnesium не привязан к каналу', $errors);
        $this->assertContains('Насос EC Micro не привязан к каналу', $errors);
    }

    #[Test]
    public function it_blocks_cycle_start_when_required_ec_pump_calibrations_are_missing(): void
    {
        $ecZone = Zone::factory()->create([
            'capabilities' => [
                'ec_control' => true,
                'ph_control' => false,
            ],
        ]);
        $this->attachRequiredInfrastructure($ecZone);

        $node = DeviceNode::factory()->create([
            'zone_id' => $ecZone->id,
            'status' => 'online',
        ]);

        $npkChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]);
        $calciumChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_b',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]);
        $magnesiumChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_c',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]);
        $microChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_d',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]);

        $this->bindChannelToRole($ecZone, $npkChannel, 'ec_npk_pump', 'Насос EC NPK');
        $this->bindChannelToRole($ecZone, $calciumChannel, 'ec_calcium_pump', 'Насос EC Calcium');
        $this->bindChannelToRole($ecZone, $magnesiumChannel, 'ec_magnesium_pump', 'Насос EC Magnesium');
        $this->bindChannelToRole($ecZone, $microChannel, 'ec_micro_pump', 'Насос EC Micro');

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$ecZone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => true,
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Zone is not ready for cycle start');

        $errors = $response->json('readiness_errors', []);
        $this->assertContains('Для насоса EC NPK не задана калибровка', $errors);
        $this->assertContains('Для насоса EC Calcium не задана калибровка', $errors);
        $this->assertContains('Для насоса EC Magnesium не задана калибровка', $errors);
        $this->assertContains('Для насоса EC Micro не задана калибровка', $errors);
    }

    #[Test]
    public function it_blocks_cycle_start_when_logic_profile_enables_dosing_but_zone_capabilities_are_stale(): void
    {
        $zone = Zone::factory()->create([
            'capabilities' => [
                'ec_control' => false,
                'ph_control' => false,
            ],
        ]);
        $this->attachRequiredInfrastructure($zone);
        $this->createPidConfigs($zone);

        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);

        $this->bindChannelToRole($zone, NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_acid',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]), 'ph_acid_pump', 'Насос pH кислоты');
        $this->bindChannelToRole($zone, NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_base',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]), 'ph_base_pump', 'Насос pH щёлочи');
        $this->bindChannelToRole($zone, NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]), 'ec_npk_pump', 'Насос EC NPK');
        $this->bindChannelToRole($zone, NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_b',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]), 'ec_calcium_pump', 'Насос EC Calcium');
        $this->bindChannelToRole($zone, NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_c',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]), 'ec_magnesium_pump', 'Насос EC Magnesium');
        $this->bindChannelToRole($zone, NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_d',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]), 'ec_micro_pump', 'Насос EC Micro');

        $this->saveZoneLogicProfile($zone, [
            'irrigation' => [
                'enabled' => true,
                'execution' => [
                    'tanks_count' => 2,
                ],
            ],
            'ph' => [
                'enabled' => true,
            ],
            'ec' => [
                'enabled' => true,
            ],
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$zone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => true,
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Zone is not ready for cycle start');

        $errors = $response->json('readiness_errors', []);
        $this->assertContains('Для насоса pH кислоты не задана калибровка', $errors);
        $this->assertContains('Для насоса pH щёлочи не задана калибровка', $errors);
        $this->assertContains('Для насоса EC NPK не задана калибровка', $errors);
        $this->assertTrue((bool) data_get($zone->fresh()->capabilities, 'ph_control'));
        $this->assertTrue((bool) data_get($zone->fresh()->capabilities, 'ec_control'));
    }

    #[Test]
    public function it_blocks_cycle_start_when_dispatch_to_automation_engine_is_disabled(): void
    {
        config()->set('services.automation_engine.grow_cycle_start_dispatch_enabled', false);
        $this->createPidConfigs($this->zone);

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => true,
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('readiness.checks.dispatch_enabled', false);

        $errors = $response->json('readiness_errors', []);
        $this->assertContains('Запуск в automation-engine отключён runtime-флагом', $errors);
    }

    #[Test]
    public function it_blocks_cycle_start_when_zone_has_active_hard_blocking_alert(): void
    {
        $this->createPidConfigs($this->zone);

        Alert::query()->create([
            'zone_id' => $this->zone->id,
            'source' => 'automation-engine',
            'code' => 'biz_zone_correction_config_missing',
            'type' => 'biz',
            'details' => [],
            'status' => 'ACTIVE',
            'category' => 'operations',
            'severity' => 'critical',
            'error_count' => 1,
            'first_seen_at' => now(),
            'last_seen_at' => now(),
            'created_at' => now(),
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => true,
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('readiness.checks.blocking_alerts_clear', false)
            ->assertJsonPath('readiness.blocking_alerts.0.code', 'biz_zone_correction_config_missing');

        $errors = $response->json('readiness_errors', []);
        $this->assertContains('Есть активный блокирующий alert: не настроен correction config зоны', $errors);
    }

    #[Test]
    public function it_starts_cycle_when_required_ec_pump_calibrations_exist(): void
    {
        $ecZone = Zone::factory()->create([
            'capabilities' => [
                'ec_control' => true,
                'ph_control' => false,
            ],
        ]);
        $this->attachRequiredInfrastructure($ecZone);
        $this->createPidConfigs($ecZone);

        $node = DeviceNode::factory()->create([
            'zone_id' => $ecZone->id,
            'status' => 'online',
        ]);

        $npkChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]);
        $calciumChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_b',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]);
        $magnesiumChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_c',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]);
        $microChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_d',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]);

        $this->bindChannelToRole($ecZone, $npkChannel, 'ec_npk_pump', 'Насос EC NPK');
        $this->bindChannelToRole($ecZone, $calciumChannel, 'ec_calcium_pump', 'Насос EC Calcium');
        $this->bindChannelToRole($ecZone, $magnesiumChannel, 'ec_magnesium_pump', 'Насос EC Magnesium');
        $this->bindChannelToRole($ecZone, $microChannel, 'ec_micro_pump', 'Насос EC Micro');

        $this->createPumpCalibration($npkChannel, 'npk', 1.0);
        $this->createPumpCalibration($calciumChannel, 'calcium', 1.0);
        $this->createPumpCalibration($magnesiumChannel, 'magnesium', 0.8);
        $this->createPumpCalibration($microChannel, 'micro', 0.8);

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$ecZone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => true,
            ]);

        $response->assertStatus(201)
            ->assertJsonPath('status', 'ok');
    }

    #[Test]
    public function it_gets_active_cycle_with_dto(): void
    {
        $service = app(GrowCycleService::class);
        $cycle = $service->createCycle($this->zone, $this->revision, $this->plant->id, ['start_immediately' => true]);

        $response = $this->actingAs($this->user)
            ->getJson("/api/zones/{$this->zone->id}/grow-cycle");

        $response->assertStatus(200)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'cycle' => [
                        'id',
                        'status',
                        'planting_at',
                        'current_stage',
                        'progress',
                        'stages',
                    ],
                    'effective_targets',
                ],
            ]);
    }

    #[Test]
    public function it_advances_phase(): void
    {
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $this->revision->id,
            'phase_index' => 1,
        ]);

        $service = app(GrowCycleService::class);
        $cycle = $service->createCycle($this->zone, $this->revision, $this->plant->id, ['start_immediately' => true]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/advance-phase");

        $response->assertStatus(200);
        $cycle->refresh();
        $this->assertEquals(1, $cycle->currentPhase->phase_index);
    }

    #[Test]
    public function it_pauses_a_cycle(): void
    {
        $this->zone->update(['status' => 'RUNNING']);
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/pause");

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::PAUSED, $cycle->status);
        $this->assertSame('PAUSED', $this->zone->fresh()->status);
    }

    #[Test]
    public function it_resumes_a_cycle(): void
    {
        $this->zone->update(['status' => 'PAUSED']);
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::PAUSED,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/resume");

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::RUNNING, $cycle->status);
        $this->assertSame('RUNNING', $this->zone->fresh()->status);
    }

    #[Test]
    public function it_harvests_a_cycle(): void
    {
        $this->zone->update(['status' => 'RUNNING']);
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/harvest", [
                'batch_label' => 'Batch-001',
            ]);

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::HARVESTED, $cycle->status);
        $this->assertEquals('Batch-001', $cycle->batch_label);
        $this->assertNotNull($cycle->actual_harvest_at);
        $this->assertSame('NEW', $this->zone->fresh()->status);
    }

    #[Test]
    public function it_aborts_a_cycle(): void
    {
        $this->zone->update(['status' => 'RUNNING']);
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/abort", [
                'notes' => 'Emergency stop',
            ]);

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::ABORTED, $cycle->status);
        $this->assertSame('NEW', $this->zone->fresh()->status);
    }

    #[Test]
    public function it_returns_422_when_pausing_non_running_cycle(): void
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::PLANNED,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/pause");

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cycle is not running');
    }

    #[Test]
    public function it_returns_422_when_resuming_non_paused_cycle(): void
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/resume");

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cycle is not paused');
    }

    #[Test]
    public function it_returns_422_when_harvesting_completed_cycle(): void
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::HARVESTED,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/harvest", [
                'batch_label' => 'Batch-002',
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cycle is already completed');
    }

    #[Test]
    public function it_returns_422_when_aborting_completed_cycle(): void
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::ABORTED,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/abort", [
                'notes' => 'Already stopped',
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cycle is already completed');
    }
}
