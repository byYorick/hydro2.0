<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\Zone;
use App\Services\NodeRegistryService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class NodeRegistryServiceTest extends TestCase
{
    use RefreshDatabase;

    private NodeRegistryService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = new NodeRegistryService();
    }

    public function test_register_node_creates_new_node(): void
    {
        $node = $this->service->registerNode(
            'nd-ph-1',
            null,
            [
                'firmware_version' => '1.0.0',
                'hardware_revision' => 'rev-A',
                'name' => 'pH Node 1',
                'type' => 'ph'
            ]
        );

        $this->assertNotNull($node->id);
        $this->assertEquals('nd-ph-1', $node->uid);
        $this->assertEquals('1.0.0', $node->fw_version);
        $this->assertEquals('rev-A', $node->hardware_revision);
        $this->assertEquals('pH Node 1', $node->name);
        $this->assertEquals('ph', $node->type);
        $this->assertTrue($node->validated);
        $this->assertNotNull($node->first_seen_at);
    }

    public function test_register_node_updates_existing_node(): void
    {
        // Create existing node
        $existing = DeviceNode::create([
            'uid' => 'nd-ph-1',
            'name' => 'Old Name',
            'fw_version' => '0.9.0',
            'validated' => false,
        ]);

        $node = $this->service->registerNode(
            'nd-ph-1',
            null,
            [
                'firmware_version' => '1.0.0',
                'name' => 'New Name'
            ]
        );

        $this->assertEquals($existing->id, $node->id);
        $this->assertEquals('1.0.0', $node->fw_version);
        $this->assertEquals('New Name', $node->name);
        $this->assertTrue($node->validated);
        // first_seen_at should not change for existing node
        $this->assertNotNull($node->first_seen_at);
    }

    public function test_register_node_with_zone_uid_ignored(): void
    {
        // КРИТИЧНО: Автопривязка отключена - zone_uid игнорируется
        $zone = Zone::factory()->create();

        $node = $this->service->registerNode(
            'nd-ph-1',
            "zn-{$zone->id}",  // zone_uid предоставлен, но должен быть проигнорирован
            []
        );

        // Узел должен остаться непривязанным (zone_id = null)
        $this->assertNull($node->zone_id);
    }

    public function test_register_node_with_numeric_zone_uid_ignored(): void
    {
        // КРИТИЧНО: Автопривязка отключена - zone_uid игнорируется
        $zone = Zone::factory()->create();

        $node = $this->service->registerNode(
            'nd-ph-1',
            (string)$zone->id,  // zone_uid предоставлен, но должен быть проигнорирован
            []
        );

        // Узел должен остаться непривязанным (zone_id = null)
        $this->assertNull($node->zone_id);
    }

    public function test_register_node_sets_validated_to_true(): void
    {
        $node = $this->service->registerNode('nd-ph-1', null, []);

        $this->assertTrue($node->validated);
        $this->assertEquals('unknown', $node->type);
    }

    public function test_register_node_sets_first_seen_at_on_first_registration(): void
    {
        $node = $this->service->registerNode('nd-ph-1', null, []);

        $this->assertNotNull($node->first_seen_at);
    }

    public function test_register_node_sets_unknown_for_legacy_type_alias(): void
    {
        $node = $this->service->registerNode(
            'nd-irrig-legacy',
            null,
            [
                'type' => 'pump_node',
            ]
        );

        $this->assertEquals('unknown', $node->type);
    }

    public function test_register_node_from_hello_sets_unknown_for_legacy_alias(): void
    {
        $node = $this->service->registerNodeFromHello([
            'hardware_id' => 'esp32-test-irrig-001',
            'node_type' => 'PUMP_NODE',
            'fw_version' => '1.0.0',
        ]);

        $this->assertNotNull($node->id);
        $this->assertEquals('unknown', $node->type);
    }

    public function test_register_node_from_hello_normalizes_canonical_node_type_case(): void
    {
        $node = $this->service->registerNodeFromHello([
            'hardware_id' => 'esp32-test-irrig-002',
            'node_type' => 'IRRIG',
            'fw_version' => '1.0.0',
        ]);

        $this->assertNotNull($node->id);
        $this->assertEquals('irrig', $node->type);
    }

    public function test_register_node_preserves_first_seen_at_on_update(): void
    {
        $existing = DeviceNode::create([
            'uid' => 'nd-ph-1',
            'first_seen_at' => now()->subDays(5),
        ]);

        $node = $this->service->registerNode('nd-ph-1', null, []);

        $this->assertEquals(
            $existing->first_seen_at->format('Y-m-d H:i:s'),
            $node->first_seen_at->format('Y-m-d H:i:s')
        );
    }
}
