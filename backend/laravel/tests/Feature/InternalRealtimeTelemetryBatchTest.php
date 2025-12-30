<?php

namespace Tests\Feature;

use App\Events\TelemetryBatchUpdated;
use App\Models\DeviceNode;
use App\Models\Zone;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Event;
use Tests\TestCase;

class InternalRealtimeTelemetryBatchTest extends TestCase
{
    use RefreshDatabase;

    public function test_batches_updates_by_zone_and_broadcasts(): void
    {
        Event::fake();

        config(['services.python_bridge.token' => 'test-token']);

        $zoneA = Zone::factory()->create();
        $zoneB = Zone::factory()->create();
        $nodeA = DeviceNode::factory()->create(['zone_id' => $zoneA->id]);
        $nodeB = DeviceNode::factory()->create(['zone_id' => $zoneB->id]);

        $payload = [
            'updates' => [
                [
                    'zone_id' => $zoneA->id,
                    'node_id' => $nodeA->id,
                    'channel' => 'ph_sensor',
                    'metric_type' => 'PH',
                    'value' => 6.2,
                    'timestamp' => 1700000000000,
                ],
                [
                    'zone_id' => $zoneB->id,
                    'node_id' => $nodeB->id,
                    'channel' => 'ec_sensor',
                    'metric_type' => 'EC',
                    'value' => 1.5,
                    'timestamp' => 1700000000001,
                ],
            ],
        ];

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/internal/realtime/telemetry-batch', $payload);

        $response->assertOk();

        Event::assertDispatchedTimes(TelemetryBatchUpdated::class, 2);
        Event::assertDispatched(TelemetryBatchUpdated::class, function ($event) use ($zoneA) {
            return $event->zoneId === $zoneA->id
                && count($event->updates) === 1;
        });
        Event::assertDispatched(TelemetryBatchUpdated::class, function ($event) use ($zoneB) {
            return $event->zoneId === $zoneB->id
                && count($event->updates) === 1;
        });
    }

    public function test_rejects_payloads_exceeding_size_limit(): void
    {
        Event::fake();

        config([
            'services.python_bridge.token' => 'test-token',
            'realtime.telemetry_batch_max_bytes' => 1,
        ]);

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $payload = [
            'updates' => [
                [
                    'zone_id' => $zone->id,
                    'node_id' => $node->id,
                    'channel' => 'ph_sensor',
                    'metric_type' => 'PH',
                    'value' => 6.2,
                    'timestamp' => 1700000000000,
                ],
            ],
        ];

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/internal/realtime/telemetry-batch', $payload);

        $response->assertStatus(413);
        Event::assertNotDispatched(TelemetryBatchUpdated::class);
    }
}
