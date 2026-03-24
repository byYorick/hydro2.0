<?php

namespace Tests\Unit\Services;

use App\Models\Alert;
use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\ZoneReadinessService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneReadinessServiceTest extends TestCase
{
    use RefreshDatabase;

    private ZoneReadinessService $service;

    private string|false $previousAppEnv;

    protected function setUp(): void
    {
        parent::setUp();

        $this->previousAppEnv = getenv('APP_ENV');
        putenv('APP_ENV=production');

        config()->set('zones.readiness.strict_mode', true);
        config()->set('zones.readiness.e2e_mode', false);
        config()->set('zones.readiness.required_bindings', ['main_pump', 'drain']);
        config()->set('services.automation_engine.grow_cycle_start_dispatch_enabled', true);

        $this->service = app(ZoneReadinessService::class);
    }

    protected function tearDown(): void
    {
        if ($this->previousAppEnv === false) {
            putenv('APP_ENV');
        } else {
            putenv('APP_ENV='.$this->previousAppEnv);
        }

        parent::tearDown();
    }

    private function createPidConfigs(Zone $zone): void
    {
        $documents = app(AutomationConfigDocumentService::class);

        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH,
            AutomationConfigRegistry::SCOPE_ZONE,
            (int) $zone->id,
            [
                'target' => 5.8,
                'dead_zone' => 0.05,
                'close_zone' => 0.3,
                'far_zone' => 1.0,
                'zone_coeffs' => [
                    'close' => ['kp' => 5.0, 'ki' => 0.05, 'kd' => 0.0],
                    'far' => ['kp' => 8.0, 'ki' => 0.02, 'kd' => 0.0],
                ],
                'max_output' => 20.0,
                'min_interval_ms' => 90000,
                'max_integral' => 20.0,
            ]
        );

        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_PID_EC,
            AutomationConfigRegistry::SCOPE_ZONE,
            (int) $zone->id,
            [
                'target' => 1.6,
                'dead_zone' => 0.1,
                'close_zone' => 0.5,
                'far_zone' => 1.5,
                'zone_coeffs' => [
                    'close' => ['kp' => 30.0, 'ki' => 0.3, 'kd' => 0.0],
                    'far' => ['kp' => 50.0, 'ki' => 0.1, 'kd' => 0.0],
                ],
                'max_output' => 50.0,
                'min_interval_ms' => 120000,
                'max_integral' => 100.0,
            ]
        );
    }

    public function test_check_zone_readiness_detects_missing_ec_roles_when_ec_control_enabled(): void
    {
        $zone = Zone::factory()->create([
            'capabilities' => [
                'ec_control' => true,
                'ph_control' => false,
            ],
        ]);

        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);

        $this->createActuatorBinding($zone, $node, 'pump_main', 'main_pump', 'Основная помпа');
        $this->createActuatorBinding($zone, $node, 'drain_main', 'drain', 'Дренаж');

        $readiness = $this->service->checkZoneReadiness($zone);

        $this->assertFalse($readiness['ready']);
        $this->assertEquals(
            ['ec_npk_pump', 'ec_calcium_pump', 'ec_magnesium_pump', 'ec_micro_pump'],
            $readiness['missing_bindings']
        );
    }

    public function test_check_zone_readiness_is_ready_when_all_required_roles_present(): void
    {
        $zone = Zone::factory()->create([
            'capabilities' => [
                'ec_control' => true,
                'ph_control' => true,
            ],
        ]);

        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);

        $this->createActuatorBinding($zone, $node, 'pump_main', 'main_pump', 'Основная помпа');
        $this->createActuatorBinding($zone, $node, 'drain_main', 'drain', 'Дренаж');
        $this->createActuatorBinding($zone, $node, 'pump_acid', 'ph_acid_pump', 'Насос pH кислоты', withCalibration: true);
        $this->createActuatorBinding($zone, $node, 'pump_base', 'ph_base_pump', 'Насос pH щёлочи', withCalibration: true);
        $this->createActuatorBinding($zone, $node, 'pump_a', 'ec_npk_pump', 'Насос EC NPK', withCalibration: true);
        $this->createActuatorBinding($zone, $node, 'pump_b', 'ec_calcium_pump', 'Насос EC Calcium', withCalibration: true);
        $this->createActuatorBinding($zone, $node, 'pump_c', 'ec_magnesium_pump', 'Насос EC Magnesium', withCalibration: true);
        $this->createActuatorBinding($zone, $node, 'pump_d', 'ec_micro_pump', 'Насос EC Micro', withCalibration: true);
        $this->createPidConfigs($zone);

        $readiness = $this->service->checkZoneReadiness($zone);

        $this->assertTrue($readiness['ready']);
        $this->assertEmpty($readiness['missing_bindings']);
    }

    public function test_validate_recognizes_uppercase_online_status_and_returns_warnings(): void
    {
        $zone = Zone::factory()->create();

        $onlineNode = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'ONLINE',
        ]);
        $offlineNode = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'offline',
        ]);

        $this->createActuatorBinding($zone, $onlineNode, 'pump_main', 'main_pump', 'Основная помпа');
        $this->createActuatorBinding($zone, $onlineNode, 'drain_main', 'drain', 'Дренаж');
        $this->createActuatorBinding($zone, $offlineNode, 'fan_main', 'vent', 'Вентиляция');
        $this->createPidConfigs($zone);

        $result = $this->service->validate($zone->id);

        $this->assertTrue($result['valid']);
        $this->assertContains('1 нода офлайн', $result['warnings']);
    }

    public function test_check_zone_readiness_ignores_unbound_nodes_for_online_check(): void
    {
        $zone = Zone::factory()->create();

        $boundOnlineNode = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'offline',
        ]);

        $this->createActuatorBinding($zone, $boundOnlineNode, 'pump_main', 'main_pump', 'Основная помпа');
        $this->createActuatorBinding($zone, $boundOnlineNode, 'drain_main', 'drain', 'Дренаж');
        $this->createPidConfigs($zone);

        $readiness = $this->service->checkZoneReadiness($zone);

        $this->assertTrue($readiness['ready']);
        $this->assertSame(1, $readiness['nodes']['total']);
        $this->assertSame(1, $readiness['nodes']['online']);
        $this->assertEmpty($readiness['warnings']);
    }

    public function test_check_zone_readiness_accepts_greenhouse_level_bindings(): void
    {
        $zone = Zone::factory()->create();

        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);

        $this->createActuatorBinding(
            $zone,
            $node,
            'pump_main',
            'main_pump',
            'Основная помпа',
            ownerType: 'greenhouse'
        );
        $this->createActuatorBinding(
            $zone,
            $node,
            'drain_main',
            'drain',
            'Дренаж',
            ownerType: 'greenhouse'
        );
        $this->createPidConfigs($zone);

        $readiness = $this->service->checkZoneReadiness($zone);

        $this->assertTrue($readiness['ready']);
        $this->assertEmpty($readiness['missing_bindings']);
        $this->assertTrue($readiness['checks']['main_pump']);
        $this->assertTrue($readiness['checks']['drain']);
        $this->assertTrue($readiness['checks']['online_nodes']);
    }

    public function test_check_zone_readiness_counts_zone_nodes_when_bindings_absent(): void
    {
        $zone = Zone::factory()->create();

        DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);

        $readiness = $this->service->checkZoneReadiness($zone);

        $this->assertFalse($readiness['ready']);
        $this->assertSame(1, $readiness['nodes']['total']);
        $this->assertSame(1, $readiness['nodes']['online']);
        $this->assertTrue($readiness['checks']['has_nodes']);
        $this->assertTrue($readiness['checks']['online_nodes']);
        $this->assertContains('main_pump', $readiness['missing_bindings']);
        $this->assertContains('drain', $readiness['missing_bindings']);
        $this->assertNotContains('Zone has no bound nodes', $readiness['errors']);
    }

    public function test_check_zone_readiness_does_not_require_drain_for_two_tank_topology(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);

        $this->createActuatorBinding($zone, $node, 'pump_main', 'main_pump', 'Основная помпа');
        $this->createPidConfigs($zone);

        $this->storeZoneLogicProfile($zone, [
            'irrigation' => [
                'enabled' => true,
                'execution' => [
                    'tanks_count' => 2,
                ],
            ],
        ]);

        $readiness = $this->service->checkZoneReadiness($zone);

        $this->assertTrue($readiness['ready']);
        $this->assertSame(['main_pump'], $readiness['required_bindings']);
        $this->assertArrayNotHasKey('drain', $readiness['checks']);
        $this->assertEmpty($readiness['missing_bindings']);
    }

    public function test_check_zone_readiness_requires_drain_for_three_tank_topology(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);

        $this->createActuatorBinding($zone, $node, 'pump_main', 'main_pump', 'Основная помпа');

        $this->storeZoneLogicProfile($zone, [
            'irrigation' => [
                'enabled' => true,
                'execution' => [
                    'tanks_count' => 3,
                ],
            ],
        ]);

        $readiness = $this->service->checkZoneReadiness($zone);

        $this->assertFalse($readiness['ready']);
        $this->assertContains('drain', $readiness['required_bindings']);
        $this->assertContains('drain', $readiness['missing_bindings']);
        $this->assertFalse($readiness['checks']['drain']);
    }

    private function createActuatorBinding(
        Zone $zone,
        DeviceNode $node,
        string $channel,
        string $role,
        string $label,
        string $ownerType = 'zone',
        bool $withCalibration = false
    ): void
    {
        $nodeChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => $channel,
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => $withCalibration ? ['pump_calibration' => ['ml_per_sec' => 1.25]] : [],
        ]);

        $instance = InfrastructureInstance::query()->firstOrCreate(
            [
                'owner_type' => $ownerType,
                'owner_id' => $ownerType === 'greenhouse' ? $zone->greenhouse_id : $zone->id,
                'label' => $label,
            ],
            [
                'asset_type' => 'PUMP',
                'required' => true,
            ]
        );

        ChannelBinding::query()->updateOrCreate(
            ['node_channel_id' => $nodeChannel->id],
            [
                'infrastructure_instance_id' => $instance->id,
                'direction' => 'actuator',
                'role' => $role,
            ]
        );
    }

    /**
     * @param  array<string, mixed>  $subsystems
     */
    private function storeZoneLogicProfile(Zone $zone, array $subsystems): void
    {
        app(AutomationConfigDocumentService::class)->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
            AutomationConfigRegistry::SCOPE_ZONE,
            (int) $zone->id,
            [
                'active_mode' => 'working',
                'profiles' => [
                    'working' => [
                        'mode' => 'working',
                        'is_active' => true,
                        'subsystems' => $subsystems,
                    ],
                ],
            ]
        );
    }

    public function test_check_zone_readiness_accepts_string_capabilities_as_enabled(): void
    {
        $zone = Zone::factory()->create([
            'capabilities' => [
                'ec_control' => 'true',
                'ph_control' => '1',
            ],
        ]);

        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);

        $this->createActuatorBinding($zone, $node, 'pump_main', 'main_pump', 'Основная помпа');
        $this->createActuatorBinding($zone, $node, 'drain_main', 'drain', 'Дренаж');

        $readiness = $this->service->checkZoneReadiness($zone);

        $this->assertFalse($readiness['ready']);
        $this->assertContains('ph_acid_pump', $readiness['missing_bindings']);
        $this->assertContains('ec_npk_pump', $readiness['missing_bindings']);
    }

    public function test_check_zone_readiness_is_not_ready_when_dispatch_is_disabled(): void
    {
        config()->set('services.automation_engine.grow_cycle_start_dispatch_enabled', false);

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);

        $this->createActuatorBinding($zone, $node, 'pump_main', 'main_pump', 'Основная помпа');
        $this->createActuatorBinding($zone, $node, 'drain_main', 'drain', 'Дренаж');

        $readiness = $this->service->checkZoneReadiness($zone);

        $this->assertFalse($readiness['ready']);
        $this->assertFalse($readiness['checks']['dispatch_enabled']);
        $this->assertContains('Запуск в automation-engine отключён runtime-флагом', $readiness['errors']);
    }

    public function test_check_zone_readiness_detects_hard_blocking_alerts(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);

        $this->createActuatorBinding($zone, $node, 'pump_main', 'main_pump', 'Основная помпа');
        $this->createActuatorBinding($zone, $node, 'drain_main', 'drain', 'Дренаж');

        Alert::query()->create([
            'zone_id' => $zone->id,
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

        $readiness = $this->service->checkZoneReadiness($zone);

        $this->assertFalse($readiness['ready']);
        $this->assertFalse($readiness['checks']['blocking_alerts_clear']);
        $this->assertCount(1, $readiness['blocking_alerts']);
        $this->assertContains('Есть активный блокирующий alert: не настроен correction config зоны', $readiness['errors']);
    }
}
