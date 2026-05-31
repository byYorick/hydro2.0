<?php

namespace Tests\Unit\Services;

use App\Enums\NodeLifecycleState;
use App\Exceptions\ZoneNodeAutomationBindingException;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Sensor;
use App\Models\Zone;
use App\Services\ZoneNodeAutomationBindingValidator;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneNodeAutomationBindingValidatorTest extends TestCase
{
    use RefreshDatabase;

    public function test_allows_bind_when_zone_has_no_conflicting_nodes(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);
        NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'ec_sensor',
            'type' => 'sensor',
            'metric' => 'EC',
            'unit' => null,
            'config' => [],
            'is_active' => true,
        ]);

        $validator = new ZoneNodeAutomationBindingValidator;
        $validator->assertBindAllowed($node, $zone->id);

        $this->assertTrue(true);
    }

    public function test_rejects_second_ec_node_when_sibling_has_ec_channel(): void
    {
        $zone = Zone::factory()->create();
        $existing = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
        ]);
        NodeChannel::create([
            'node_id' => $existing->id,
            'channel' => 'ec0',
            'type' => 'sensor',
            'metric' => 'EC',
            'unit' => null,
            'config' => [],
            'is_active' => true,
        ]);

        $incoming = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);
        NodeChannel::create([
            'node_id' => $incoming->id,
            'channel' => 'ec0',
            'type' => 'sensor',
            'metric' => 'EC',
            'unit' => null,
            'config' => [],
            'is_active' => true,
        ]);

        $validator = new ZoneNodeAutomationBindingValidator;

        $this->expectException(ZoneNodeAutomationBindingException::class);
        $validator->assertBindAllowed($incoming, $zone->id);
    }

    public function test_rejects_second_ec_when_sibling_has_active_ec_sensor_row(): void
    {
        $zone = Zone::factory()->create();
        $existing = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
        ]);
        Sensor::factory()->create([
            'zone_id' => $zone->id,
            'node_id' => $existing->id,
            'type' => 'EC',
            'is_active' => true,
        ]);

        $incoming = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);
        NodeChannel::create([
            'node_id' => $incoming->id,
            'channel' => 'ec0',
            'type' => 'sensor',
            'metric' => 'EC',
            'unit' => null,
            'config' => [],
            'is_active' => true,
        ]);

        $validator = new ZoneNodeAutomationBindingValidator;

        $this->expectException(ZoneNodeAutomationBindingException::class);
        $validator->assertBindAllowed($incoming, $zone->id);
    }
}
