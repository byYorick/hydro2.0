<?php

namespace Tests\Unit\Services;

use App\Enums\NodeLifecycleState;
use App\Events\NodeConfigUpdated;
use App\Exceptions\ZoneNodeAutomationBindingException;
use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Services\NodeFirmwareUnbindService;
use App\Services\NodeService;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\Http;
use Mockery\MockInterface;
use Tests\RefreshDatabase;
use Tests\TestCase;

class NodeServiceBindingTest extends TestCase
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
        // Только domain events: Event::fake() без аргументов глушит eloquent.saving
        // и ломает якорь pending_zone_set_at на DeviceNode.
        Event::fake([NodeConfigUpdated::class]);
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
        $this->assertNotNull($updated->pending_zone_set_at);
        $this->assertDatabaseHas('nodes', [
            'id' => $node->id,
            'pending_zone_id' => $zone->id,
            'zone_id' => null,
        ]);
    }

    public function test_attach_from_active_lifecycle_sets_pending_via_fsm(): void
    {
        $oldZone = Zone::factory()->create();
        $newZone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $oldZone->id,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::ACTIVE,
        ]);

        $updated = $this->service->update($node, ['zone_id' => $newZone->id]);

        $this->assertNull($updated->zone_id);
        $this->assertEquals($newZone->id, $updated->pending_zone_id);
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $updated->lifecycle_state);
        $this->assertNotNull($updated->pending_zone_set_at);
    }

    public function test_cannot_attach_from_degraded_or_maintenance(): void
    {
        $zone = Zone::factory()->create();

        foreach ([NodeLifecycleState::DEGRADED, NodeLifecycleState::MAINTENANCE] as $state) {
            $node = DeviceNode::factory()->create([
                'zone_id' => null,
                'lifecycle_state' => $state,
            ]);

            try {
                $this->service->update($node, ['zone_id' => $zone->id]);
                $this->fail("Expected DomainException for lifecycle {$state->value}");
            } catch (\DomainException $e) {
                $this->assertStringContainsString($state->value, $e->getMessage());
            }
        }
    }

    public function test_attach_node_clears_old_zone_id(): void
    {
        $oldZone = Zone::factory()->create();
        $newZone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $oldZone->id,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
            'config' => [
                'node_id' => 'nd-rebind-1',
                'version' => 3,
                'type' => 'ph',
                'gh_uid' => 'gh-real',
                'zone_uid' => $oldZone->uid,
                'channels' => [],
                'mqtt' => ['configured' => true],
            ],
        ]);

        $updated = $this->service->update($node, ['zone_id' => $newZone->id]);

        // Проверяем, что старый zone_id очищен, установлен новый pending_zone_id
        $this->assertEquals($newZone->id, $updated->pending_zone_id);
        $this->assertNull($updated->zone_id);
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $updated->lifecycle_state);
        $this->assertSame('gh-temp', $updated->config['gh_uid'] ?? null);
        $this->assertSame('zn-temp', $updated->config['zone_uid'] ?? null);

        Http::assertSent(function ($request) use ($node, $oldZone) {
            if (! str_contains($request->url(), "/nodes/{$node->uid}/config")) {
                return false;
            }
            $data = $request->data();

            return ($data['zone_id'] ?? null) === $oldZone->id
                && ($data['config']['gh_uid'] ?? null) === 'gh-temp'
                && ($data['config']['zone_uid'] ?? null) === 'zn-temp';
        });
    }

    public function test_cross_zone_rebind_calls_firmware_unbind_with_old_zone(): void
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
                    return (int) $boundZoneId === (int) $oldZone->id;
                })
                ->andReturn(true);
            $mock->shouldReceive('mirrorTempNamespaceInStoredConfig')
                ->once()
                ->withArgs(fn (DeviceNode $n) => $n->id !== null);
        });

        $service = app(NodeService::class);
        $updated = $service->update($node, ['zone_id' => $newZone->id]);

        $this->assertNull($updated->zone_id);
        $this->assertEquals($newZone->id, $updated->pending_zone_id);
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $updated->lifecycle_state);
    }

    public function test_first_bind_does_not_call_firmware_unbind(): void
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

        $service = app(NodeService::class);
        $updated = $service->update($node, ['zone_id' => $zone->id]);

        $this->assertNull($updated->zone_id);
        $this->assertEquals($zone->id, $updated->pending_zone_id);
    }

    public function test_same_zone_idempotent_assign_does_not_call_firmware_unbind(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
        ]);

        $this->mock(NodeFirmwareUnbindService::class, function (MockInterface $mock) {
            $mock->shouldReceive('publishTempNamespaceConfig')->never();
            $mock->shouldReceive('mirrorTempNamespaceInStoredConfig')->never();
        });

        $service = app(NodeService::class);
        $updated = $service->update($node, ['zone_id' => $zone->id]);

        $this->assertEquals($zone->id, $updated->zone_id);
        $this->assertNull($updated->pending_zone_id);
        $this->assertEquals(NodeLifecycleState::ASSIGNED_TO_ZONE, $updated->lifecycle_state);
    }

    public function test_attach_node_to_same_zone_is_idempotent(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
            'name' => 'Old name',
        ]);

        $updated = $this->service->update($node, [
            'zone_id' => $zone->id,
            'name' => 'Updated name',
        ]);

        $this->assertEquals($zone->id, $updated->zone_id);
        $this->assertNull($updated->pending_zone_id);
        $this->assertEquals(NodeLifecycleState::ASSIGNED_TO_ZONE, $updated->lifecycle_state);
        $this->assertEquals('Updated name', $updated->name);
    }

    public function test_retry_attach_for_same_pending_zone_normalizes_lifecycle_and_keeps_pending_state(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
        ]);

        $updated = $this->service->update($node, ['zone_id' => $zone->id]);

        $this->assertNull($updated->zone_id);
        $this->assertEquals($zone->id, $updated->pending_zone_id);
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $updated->lifecycle_state);
    }

    public function test_complete_binding_from_laravel_observer(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);

        // Симуляция завершения привязки внутренним Laravel observer после observed config_report.
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
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
            'config' => [
                'node_id' => 'nd-detach-1',
                'version' => 3,
                'type' => 'ph',
                'gh_uid' => 'gh-real',
                'zone_uid' => $zone->uid,
                'channels' => [],
                'mqtt' => ['configured' => true],
            ],
        ]);

        $detached = $this->service->detach($node);

        // Проверяем, что zone_id и pending_zone_id очищены
        $this->assertNull($detached->zone_id);
        $this->assertNull($detached->pending_zone_id);
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $detached->lifecycle_state);
        $this->assertSame('gh-temp', $detached->config['gh_uid'] ?? null);
        $this->assertSame('zn-temp', $detached->config['zone_uid'] ?? null);
        $this->assertDatabaseHas('nodes', [
            'id' => $node->id,
            'zone_id' => null,
            'pending_zone_id' => null,
        ]);

        Http::assertSent(function ($request) use ($node, $zone) {
            if (! str_contains($request->url(), "/nodes/{$node->uid}/config")) {
                return false;
            }
            $data = $request->data();

            return ($data['zone_id'] ?? null) === $zone->id
                && ($data['config']['gh_uid'] ?? null) === 'gh-temp'
                && ($data['config']['zone_uid'] ?? null) === 'zn-temp';
        });
    }

    public function test_detach_active_node_resets_lifecycle_via_fsm(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::ACTIVE,
        ]);

        $detached = $this->service->detach($node);

        $this->assertNull($detached->zone_id);
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $detached->lifecycle_state);
    }

    public function test_detach_node_with_pending_zone_id(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,  // Нода в процессе привязки
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);

        $detached = $this->service->detach($node);

        // Проверяем, что pending_zone_id также очищен
        $this->assertNull($detached->zone_id);
        $this->assertNull($detached->pending_zone_id);
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $detached->lifecycle_state);

        // Нода ещё в temp namespace — unbind publish не нужен
        Http::assertNothingSent();
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
        Http::assertNothingSent();
    }

    public function test_detach_continues_when_history_logger_unavailable(): void
    {
        Http::fake(function () {
            return Http::response(['error' => 'down'], 503);
        });

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
        ]);

        $detached = $this->service->detach($node);

        $this->assertNull($detached->zone_id);
        $this->assertEquals(NodeLifecycleState::REGISTERED_BACKEND, $detached->lifecycle_state);
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

    public function test_cannot_ui_attach_second_ec_node_when_zone_already_has_ec(): void
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

        $this->expectException(ZoneNodeAutomationBindingException::class);
        $this->service->update($incoming, ['zone_id' => $zone->id]);
    }

    public function test_attach_irrig_node_auto_binds_pump_main_and_drain(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => null,
            'type' => 'irrig',
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);
        NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_main',
            'type' => 'ACTUATOR',
            'metric' => 'RELAY',
            'unit' => null,
            'config' => [],
        ]);
        NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'valve_drain',
            'type' => 'ACTUATOR',
            'metric' => 'RELAY',
            'unit' => null,
            'config' => [],
        ]);

        $updated = $this->service->update($node, ['zone_id' => $zone->id]);

        $this->assertEquals($zone->id, $updated->pending_zone_id);
        $this->assertTrue(
            ChannelBinding::query()
                ->where('role', 'pump_main')
                ->whereHas('infrastructureInstance', fn ($q) => $q->where('owner_type', 'zone')->where('owner_id', $zone->id))
                ->whereHas('nodeChannel', fn ($q) => $q->where('node_id', $node->id))
                ->exists()
        );
        $this->assertTrue(
            ChannelBinding::query()
                ->where('role', 'drain')
                ->whereHas('infrastructureInstance', fn ($q) => $q->where('owner_type', 'zone')->where('owner_id', $zone->id))
                ->whereHas('nodeChannel', fn ($q) => $q->where('node_id', $node->id)->where('channel', 'valve_drain'))
                ->exists()
        );
    }

    public function test_attach_does_not_overwrite_existing_pump_main_role(): void
    {
        $zone = Zone::factory()->create();
        $owner = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'irrig',
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
        ]);
        $ownerChannel = NodeChannel::create([
            'node_id' => $owner->id,
            'channel' => 'pump_main',
            'type' => 'actuator',
            'metric' => 'RELAY',
            'unit' => null,
            'config' => [],
        ]);
        app(\App\Services\ZoneChannelAutoBinder::class)->bindFromNode($zone, $owner->fresh(['channels']));

        $incoming = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => null,
            'type' => 'irrig',
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);
        // Incoming without pump_main so ZoneNodeAutomationBindingValidator may still allow
        // (duplicate pump_main role check). Give only a non-conflicting actuator if needed.
        // If validator blocks second irrig with pump_main — create without pump_main channel
        // and assert auto-binder skips because role taken. Use valve only.
        NodeChannel::create([
            'node_id' => $incoming->id,
            'channel' => 'valve_irrigation',
            'type' => 'actuator',
            'metric' => 'RELAY',
            'unit' => null,
            'config' => [],
        ]);

        $this->service->update($incoming, ['zone_id' => $zone->id]);

        $binding = ChannelBinding::query()
            ->where('role', 'pump_main')
            ->whereHas('infrastructureInstance', fn ($q) => $q->where('owner_type', 'zone')->where('owner_id', $zone->id))
            ->first();
        $this->assertNotNull($binding);
        $this->assertSame((int) $ownerChannel->id, (int) $binding->node_channel_id);
    }

    public function test_binding_completion_auto_binds_missing_pump_main(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'type' => 'irrig',
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);
        NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_main',
            'type' => 'actuator',
            'metric' => 'RELAY',
            'unit' => null,
            'config' => [],
        ]);

        $updated = $this->service->update($node, [
            'zone_id' => $zone->id,
            'pending_zone_id' => null,
        ]);

        $this->assertEquals($zone->id, $updated->zone_id);
        $this->assertTrue(
            ChannelBinding::query()
                ->where('role', 'pump_main')
                ->whereHas('infrastructureInstance', fn ($q) => $q->where('owner_type', 'zone')->where('owner_id', $zone->id))
                ->exists()
        );
    }
}
