<?php

namespace Tests\Unit;

use App\Enums\NodeLifecycleState;
use App\Jobs\PublishNodeConfigJob;
use App\Models\DeviceNode;
use App\Models\Zone;
use Illuminate\Support\Facades\Event;
use Tests\RefreshDatabase;
use Tests\TestCase;

class PublishNodeConfigJobTest extends TestCase
{
    use RefreshDatabase;

    public function test_failed_does_not_rollback_pending_bind_intent(): void
    {
        Event::fake();

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);

        $job = new PublishNodeConfigJob($node->id);
        $job->failed(new \RuntimeException('history-logger unavailable'));

        $node->refresh();
        $this->assertNull($node->zone_id);
        $this->assertSame($zone->id, $node->pending_zone_id);
        $this->assertSame(NodeLifecycleState::REGISTERED_BACKEND, $node->lifecycle_state);
    }
}
