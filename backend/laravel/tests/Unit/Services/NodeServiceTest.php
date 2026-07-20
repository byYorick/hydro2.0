<?php

namespace Tests\Unit\Services;

use App\Enums\NodeLifecycleState;
use App\Models\DeviceNode;
use App\Models\Zone;
use App\Services\NodeFirmwareUnbindService;
use App\Services\NodeService;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Mockery\MockInterface;
use Tests\RefreshDatabase;
use Tests\TestCase;

class NodeServiceTest extends TestCase
{
    use RefreshDatabase;

    private NodeService $service;

    protected function setUp(): void
    {
        parent::setUp();
        Config::set('services.history_logger.url', 'http://history-logger:9300');
        Config::set('services.history_logger.token', 'test-token');
        Http::fake([
            'history-logger:9300/nodes/*/config' => Http::response(['status' => 'ok'], 200),
        ]);
        $this->service = app(NodeService::class);
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
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
        ]);

        $detached = $this->service->detach($node);

        $this->assertNull($detached->zone_id);
        $this->assertNull($detached->pending_zone_id);
        $this->assertEquals(
            NodeLifecycleState::REGISTERED_BACKEND,
            $detached->lifecycle_state
        );
        $this->assertDatabaseHas('nodes', [
            'id' => $node->id,
            'zone_id' => null,
            'pending_zone_id' => null,
        ]);
    }

    public function test_ui_rebind_invokes_firmware_unbind_before_clearing_zone(): void
    {
        $oldZone = Zone::factory()->create();
        $newZone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $oldZone->id,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
        ]);

        $this->mock(NodeFirmwareUnbindService::class, function (MockInterface $mock) use ($oldZone) {
            $mock->shouldReceive('publishTempNamespaceConfig')
                ->once()
                ->withArgs(function (DeviceNode $n, ?int $boundZoneId) use ($oldZone) {
                    return $n->zone_id === $oldZone->id
                        && (int) $boundZoneId === (int) $oldZone->id;
                })
                ->andReturn(true);
            $mock->shouldReceive('mirrorTempNamespaceInStoredConfig')->once();
        });

        $updated = app(NodeService::class)->update($node, ['zone_id' => $newZone->id]);

        $this->assertNull($updated->zone_id);
        $this->assertEquals($newZone->id, $updated->pending_zone_id);
    }

    public function test_ui_first_bind_skips_firmware_unbind(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);

        $this->mock(NodeFirmwareUnbindService::class, function (MockInterface $mock) {
            $mock->shouldReceive('publishTempNamespaceConfig')->never();
            $mock->shouldReceive('mirrorTempNamespaceInStoredConfig')->never();
        });

        $updated = app(NodeService::class)->update($node, ['zone_id' => $zone->id]);

        $this->assertNull($updated->zone_id);
        $this->assertEquals($zone->id, $updated->pending_zone_id);
    }
}
