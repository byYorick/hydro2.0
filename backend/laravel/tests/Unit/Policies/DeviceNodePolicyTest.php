<?php

namespace Tests\Unit\Policies;

use App\Models\DeviceNode;
use App\Models\User;
use App\Models\Zone;
use App\Policies\DeviceNodePolicy;
use Tests\RefreshDatabase;
use Tests\TestCase;

class DeviceNodePolicyTest extends TestCase
{
    use RefreshDatabase;

    private DeviceNodePolicy $policy;

    protected function setUp(): void
    {
        parent::setUp();
        $this->policy = new DeviceNodePolicy();
    }

    public function test_viewer_can_view_nodes(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $this->assertTrue($this->policy->view($user, $node));
    }

    public function test_operator_can_update_nodes(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $this->assertTrue($this->policy->update($user, $node));
    }

    public function test_viewer_cannot_update_nodes(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $this->assertFalse($this->policy->update($user, $node));
    }

    public function test_operator_can_publish_config(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $this->assertTrue($this->policy->publishConfig($user, $node));
    }

    public function test_operator_can_send_commands(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $this->assertTrue($this->policy->sendCommand($user, $node));
    }
}
