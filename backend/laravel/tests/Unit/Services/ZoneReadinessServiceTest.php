<?php

namespace Tests\Unit\Services;

use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\Zone;
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
        $this->createActuatorBinding($zone, $node, 'pump_acid', 'ph_acid_pump', 'Насос pH кислоты');
        $this->createActuatorBinding($zone, $node, 'pump_base', 'ph_base_pump', 'Насос pH щёлочи');
        $this->createActuatorBinding($zone, $node, 'pump_a', 'ec_npk_pump', 'Насос EC NPK');
        $this->createActuatorBinding($zone, $node, 'pump_b', 'ec_calcium_pump', 'Насос EC Calcium');
        $this->createActuatorBinding($zone, $node, 'pump_c', 'ec_magnesium_pump', 'Насос EC Magnesium');
        $this->createActuatorBinding($zone, $node, 'pump_d', 'ec_micro_pump', 'Насос EC Micro');

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

        $result = $this->service->validate($zone->id);

        $this->assertTrue($result['valid']);
        $this->assertContains('1 node(s) are offline', $result['warnings']);
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

        $readiness = $this->service->checkZoneReadiness($zone);

        $this->assertTrue($readiness['ready']);
        $this->assertSame(1, $readiness['nodes']['total']);
        $this->assertSame(1, $readiness['nodes']['online']);
        $this->assertEmpty($readiness['warnings']);
    }

    private function createActuatorBinding(
        Zone $zone,
        DeviceNode $node,
        string $channel,
        string $role,
        string $label
    ): void
    {
        $nodeChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => $channel,
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]);

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
            ['node_channel_id' => $nodeChannel->id],
            [
                'infrastructure_instance_id' => $instance->id,
                'direction' => 'actuator',
                'role' => $role,
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
}
