<?php

namespace Tests\Unit\Services;

use App\Enums\NodeLifecycleState;
use App\Models\DeviceNode;
use App\Models\Zone;
use App\Services\NodeLifecycleService;
use App\Services\NodeService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Event;
use Tests\TestCase;

class NodeServiceBindingTest extends TestCase
{
    use RefreshDatabase;

    private NodeService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = new NodeService(
            app(NodeLifecycleService::class)
        );
        Event::fake(); // Отключаем события для изоляции тестов
    }

    public function test_attach_node_to_zone_sets_pending_zone_id(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);

        $updated = $this->service->update($node, ['zone_id' => $zone->id]);

        // Проверяем, что pending_zone_id установлен, а zone_id очищен
        $this->assertEquals($zone->id, $updated->pending_zone_id);
        $this->assertNull($updated->zone_id);
        $this->assertDatabaseHas('nodes', [
            'id' => $node->id,
            'pending_zone_id' => $zone->id,
            'zone_id' => null,
        ]);
    }

    public function test_attach_node_clears_old_zone_id(): void
    {
        $oldZone = Zone::factory()->create();
        $newZone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $oldZone->id,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
        ]);

        $updated = $this->service->update($node, ['zone_id' => $newZone->id]);

        // Проверяем, что старый zone_id очищен, установлен новый pending_zone_id
        $this->assertEquals($newZone->id, $updated->pending_zone_id);
        $this->assertNull($updated->zone_id);
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $updated->lifecycle_state);
    }

    public function test_complete_binding_from_history_logger(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);

        // Симуляция завершения привязки от history-logger
        // History Logger отправляет zone_id и pending_zone_id=null
        $updated = $this->service->update($node, [
            'zone_id' => $zone->id,
            'pending_zone_id' => null,
        ]);

        // Проверяем, что zone_id установлен, pending_zone_id очищен
        $this->assertEquals($zone->id, $updated->zone_id);
        $this->assertNull($updated->pending_zone_id);
        $this->assertDatabaseHas('nodes', [
            'id' => $node->id,
            'zone_id' => $zone->id,
            'pending_zone_id' => null,
        ]);
    }

    public function test_detach_node_clears_pending_zone_id(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'pending_zone_id' => null,
        ]);

        $detached = $this->service->detach($node);

        // Проверяем, что zone_id и pending_zone_id очищены
        $this->assertNull($detached->zone_id);
        $this->assertNull($detached->pending_zone_id);
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $detached->lifecycle_state);
        $this->assertDatabaseHas('nodes', [
            'id' => $node->id,
            'zone_id' => null,
            'pending_zone_id' => null,
        ]);
    }

    public function test_detach_node_with_pending_zone_id(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,  // Нода в процессе привязки
        ]);

        $detached = $this->service->detach($node);

        // Проверяем, что pending_zone_id также очищен
        $this->assertNull($detached->zone_id);
        $this->assertNull($detached->pending_zone_id);
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $detached->lifecycle_state);
    }

    public function test_detach_already_detached_node(): void
    {
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => null,
        ]);

        $detached = $this->service->detach($node);

        // Должен вернуть ту же ноду без изменений
        $this->assertEquals($node->id, $detached->id);
        $this->assertNull($detached->zone_id);
        $this->assertNull($detached->pending_zone_id);
    }

    public function test_cannot_attach_in_invalid_lifecycle_state(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::UNPROVISIONED,
        ]);

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Cannot assign node to zone in current state: UNPROVISIONED');

        $this->service->update($node, ['zone_id' => $zone->id]);
    }
}

