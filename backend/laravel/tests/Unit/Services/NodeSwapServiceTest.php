<?php

namespace Tests\Unit\Services;

use App\Enums\NodeLifecycleState;
use App\Events\NodeConfigUpdated;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Services\NodeSwapService;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class NodeSwapServiceTest extends TestCase
{
    use RefreshDatabase;

    private NodeSwapService $service;

    protected function setUp(): void
    {
        parent::setUp();
        Config::set('services.history_logger.url', 'http://history-logger:9300');
        Config::set('services.history_logger.token', 'test-token');
        Http::fake([
            'history-logger:9300/nodes/*/config' => Http::response(['status' => 'ok'], 200),
        ]);
        $this->service = app(NodeSwapService::class);
        Event::fake([NodeConfigUpdated::class]);
    }

    public function test_swap_sets_pending_zone_id_not_zone_id(): void
    {
        $zone = Zone::factory()->create();
        $old = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'pending_zone_id' => null,
            'hardware_id' => 'hw-old-001',
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
            'type' => 'ph',
            'config' => [
                'node_id' => 'nd-old-001',
                'version' => 3,
                'type' => 'ph',
                'gh_uid' => 'gh-real',
                'zone_uid' => 'zn-real',
                'channels' => [],
                'mqtt' => ['configured' => true],
            ],
        ]);

        NodeChannel::create([
            'node_id' => $old->id,
            'channel' => 'ph',
            'type' => 'SENSOR',
            'metric' => 'PH',
            'is_active' => true,
        ]);

        $new = $this->service->swapNode($old->id, 'hw-new-001');

        $this->assertNull($new->zone_id);
        $this->assertSame($zone->id, $new->pending_zone_id);
        $this->assertNotNull($new->pending_zone_set_at);
        $this->assertSame(NodeLifecycleState::REGISTERED_BACKEND, $new->lifecycle_state);

        $newSecret = $new->config['node_secret'] ?? null;
        $this->assertIsString($newSecret);
        $this->assertSame(64, strlen($newSecret));
        $this->assertMatchesRegularExpression('/^[a-f0-9]{64}$/', $newSecret);

        $old->refresh();
        $this->assertNull($old->zone_id);
        $this->assertNull($old->pending_zone_id);
        $this->assertSame(NodeLifecycleState::DECOMMISSIONED, $old->lifecycle_state);
        $this->assertSame('gh-temp', $old->config['gh_uid'] ?? null);
        $this->assertSame('zn-temp', $old->config['zone_uid'] ?? null);

        $this->assertDatabaseHas('node_channels', [
            'node_id' => $new->id,
            'channel' => 'ph',
        ]);

        Http::assertSent(function ($request) use ($old, $zone) {
            return $request->url() === "http://history-logger:9300/nodes/{$old->uid}/config"
                && ($request->data()['zone_id'] ?? null) === $zone->id
                && ($request->data()['config']['gh_uid'] ?? null) === 'gh-temp'
                && ($request->data()['config']['zone_uid'] ?? null) === 'zn-temp';
        });
    }

    public function test_swap_unbind_does_not_block_pending_flow_when_hl_fails(): void
    {
        Http::fake([
            'history-logger:9300/nodes/*/config' => Http::response(['error' => 'offline'], 503),
        ]);

        $zone = Zone::factory()->create();
        $old = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'hardware_id' => 'hw-old-hl-fail',
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
            'type' => 'ec',
        ]);

        $new = $this->service->swapNode($old->id, 'hw-new-hl-fail');

        $this->assertNull($new->zone_id);
        $this->assertSame($zone->id, $new->pending_zone_id);
        $old->refresh();
        $this->assertSame(NodeLifecycleState::DECOMMISSIONED, $old->lifecycle_state);
    }

    public function test_swap_from_pending_old_node_skips_firmware_unbind(): void
    {
        Http::fake();

        $zone = Zone::factory()->create();
        $old = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'hardware_id' => 'hw-old-004',
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);

        $new = $this->service->swapNode($old->id, 'hw-new-004');

        $this->assertNull($new->zone_id);
        $this->assertSame($zone->id, $new->pending_zone_id);
        $old->refresh();
        $this->assertSame(NodeLifecycleState::DECOMMISSIONED, $old->lifecycle_state);
        Http::assertNothingSent();
    }

    public function test_swap_rejects_unassigned_old_node(): void
    {
        $old = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => null,
            'hardware_id' => 'hw-old-002',
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('not assigned or pending');

        $this->service->swapNode($old->id, 'hw-new-002');
    }

    public function test_swap_rejects_replacement_already_on_another_zone(): void
    {
        $zoneA = Zone::factory()->create();
        $zoneB = Zone::factory()->create();

        $old = DeviceNode::factory()->create([
            'zone_id' => $zoneA->id,
            'hardware_id' => 'hw-old-003',
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
        ]);

        DeviceNode::factory()->create([
            'zone_id' => $zoneB->id,
            'hardware_id' => 'hw-existing-003',
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
        ]);

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('already assigned to another zone');

        $this->service->swapNode($old->id, 'hw-existing-003');
    }
}
