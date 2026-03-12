<?php

namespace Tests\Unit\Services;

use App\Models\DeviceNode;
use App\Services\NodeLifecycleService;
use App\Services\NodeService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class NodeServiceTest extends TestCase
{
    use RefreshDatabase;

    private NodeService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = new NodeService(
            app(NodeLifecycleService::class)
        );
    }

    public function test_create_node(): void
    {
        $data = [
            'uid' => 'test-node-001',
            'name' => 'Test Node',
            'type' => 'ph',
            'status' => 'online',
        ];

        $node = $this->service->create($data);

        $this->assertInstanceOf(DeviceNode::class, $node);
        $this->assertEquals('test-node-001', $node->uid);
        $this->assertDatabaseHas('nodes', [
            'id' => $node->id,
            'uid' => 'test-node-001',
        ]);
    }

    public function test_update_node(): void
    {
        $node = DeviceNode::factory()->create(['name' => 'Old Name']);

        $updated = $this->service->update($node, ['name' => 'New Name']);

        $this->assertEquals('New Name', $updated->name);
        $this->assertDatabaseHas('nodes', [
            'id' => $node->id,
            'name' => 'New Name',
        ]);
    }

    public function test_delete_node_without_dependencies(): void
    {
        $node = DeviceNode::factory()->create(['zone_id' => null]);

        $this->service->delete($node);

        $this->assertDatabaseMissing('nodes', ['id' => $node->id]);
    }

    public function test_delete_node_attached_to_zone_throws_exception(): void
    {
        $zone = \App\Models\Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Cannot delete node that is attached to a zone');

        $this->service->delete($node);
    }

    public function test_detach_node(): void
    {
        $zone = \App\Models\Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'pending_zone_id' => null,
        ]);

        $detached = $this->service->detach($node);

        $this->assertNull($detached->zone_id);
        $this->assertNull($detached->pending_zone_id);
        $this->assertDatabaseHas('nodes', [
            'id' => $node->id,
            'zone_id' => null,
            'pending_zone_id' => null,
        ]);
    }
}
