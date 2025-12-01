<?php

namespace Tests\Unit\Services;

use App\Enums\NodeLifecycleState;
use App\Models\DeviceNode;
use App\Services\NodeLifecycleService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class NodeLifecycleServiceTest extends TestCase
{
    use RefreshDatabase;

    private NodeLifecycleService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = app(NodeLifecycleService::class);
    }

    public function test_transitions_node_to_active_state_and_sets_status_online(): void
    {
        $node = DeviceNode::factory()->create([
            'uid' => 'nd-test-assign',
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
            'status' => 'offline',
        ]);

        $result = $this->service->transitionToActive($node, 'commissioned');

        $this->assertTrue($result);

        $node->refresh();

        $this->assertEquals(NodeLifecycleState::ACTIVE, $node->lifecycle_state);
        $this->assertEquals('online', $node->status);
    }

    public function test_prevents_invalid_transitions_and_keeps_state_unchanged(): void
    {
        $node = DeviceNode::factory()->create([
            'uid' => 'nd-test-invalid',
            'lifecycle_state' => NodeLifecycleState::MANUFACTURED,
            'status' => 'offline',
        ]);

        $result = $this->service->transitionToActive($node);

        $this->assertFalse($result);

        $node->refresh();

        $this->assertEquals(NodeLifecycleState::MANUFACTURED, $node->lifecycle_state);
        $this->assertEquals('offline', $node->status);
    }

    public function test_sets_node_offline_when_transitioning_to_maintenance(): void
    {
        $node = DeviceNode::factory()->create([
            'uid' => 'nd-test-maint',
            'lifecycle_state' => NodeLifecycleState::ACTIVE,
            'status' => 'online',
        ]);

        $result = $this->service->transitionToMaintenance($node, 'manual-check');

        $this->assertTrue($result);

        $node->refresh();

        $this->assertEquals(NodeLifecycleState::MAINTENANCE, $node->lifecycle_state);
        $this->assertEquals('offline', $node->status);
    }
}
