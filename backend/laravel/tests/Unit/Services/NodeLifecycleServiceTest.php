<?php

namespace Tests\Unit\Services;

use App\Enums\NodeLifecycleState;
use App\Models\DeviceNode;
use App\Services\NodeLifecycleService;
use Tests\RefreshDatabase;
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

    public function test_allows_assigned_to_registered_for_rebind_detach(): void
    {
        $node = DeviceNode::factory()->create([
            'uid' => 'nd-test-unassign',
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
        ]);

        $result = $this->service->transitionToRegistered($node, 'reassign_to_another_zone');

        $this->assertTrue($result);
        $node->refresh();
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $node->lifecycle_state);
    }

    public function test_allows_active_to_registered_for_rebind_detach(): void
    {
        $node = DeviceNode::factory()->create([
            'uid' => 'nd-test-active-unassign',
            'lifecycle_state' => NodeLifecycleState::ACTIVE,
            'status' => 'online',
        ]);

        $result = $this->service->transitionToRegistered($node, 'explicit_detach');

        $this->assertTrue($result);
        $node->refresh();
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $node->lifecycle_state);
    }

    public function test_allows_degraded_and_maintenance_to_registered(): void
    {
        $degraded = DeviceNode::factory()->create([
            'uid' => 'nd-test-degraded-unassign',
            'lifecycle_state' => NodeLifecycleState::DEGRADED,
        ]);
        $maintenance = DeviceNode::factory()->create([
            'uid' => 'nd-test-maint-unassign',
            'lifecycle_state' => NodeLifecycleState::MAINTENANCE,
        ]);

        $this->assertTrue($this->service->transitionToRegistered($degraded, 'explicit_detach'));
        $this->assertTrue($this->service->transitionToRegistered($maintenance, 'explicit_detach'));

        $degraded->refresh();
        $maintenance->refresh();

        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $degraded->lifecycle_state);
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $maintenance->lifecycle_state);
    }

    public function test_is_transition_allowed_for_unassign_paths(): void
    {
        $this->assertTrue($this->service->isTransitionAllowed(
            NodeLifecycleState::ASSIGNED_TO_ZONE,
            NodeLifecycleState::REGISTERED_BACKEND
        ));
        $this->assertTrue($this->service->isTransitionAllowed(
            NodeLifecycleState::ACTIVE,
            NodeLifecycleState::REGISTERED_BACKEND
        ));
        $this->assertFalse($this->service->isTransitionAllowed(
            NodeLifecycleState::UNPROVISIONED,
            NodeLifecycleState::REGISTERED_BACKEND
        ));
    }

    public function test_ensure_registered_walks_from_unprovisioned(): void
    {
        $node = DeviceNode::factory()->create([
            'uid' => 'nd-test-ensure-reg',
            'lifecycle_state' => NodeLifecycleState::UNPROVISIONED,
        ]);

        $this->assertTrue($this->service->ensureRegistered($node, 'primary_registration'));

        $node->refresh();
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $node->lifecycle_state);
    }

    public function test_model_helpers_delegate_to_fsm_and_reject_invalid(): void
    {
        $node = DeviceNode::factory()->create([
            'uid' => 'nd-test-model-invalid',
            'lifecycle_state' => NodeLifecycleState::MANUFACTURED,
            'status' => 'offline',
        ]);

        $this->assertFalse($node->transitionToActive());

        $node->refresh();
        $this->assertEquals(NodeLifecycleState::MANUFACTURED, $node->lifecycle_state);
        $this->assertEquals('offline', $node->status);
    }

    public function test_model_helpers_perform_allowed_transition_via_fsm(): void
    {
        $node = DeviceNode::factory()->create([
            'uid' => 'nd-test-model-ok',
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
            'status' => 'offline',
        ]);

        $this->assertTrue($node->transitionToActive('model_helper'));

        $node->refresh();
        $this->assertEquals(NodeLifecycleState::ACTIVE, $node->lifecycle_state);
        $this->assertEquals('online', $node->status);
    }
}
