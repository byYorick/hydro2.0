<?php

namespace Tests\Feature;

use App\Enums\NodeLifecycleState;
use App\Models\DeviceNode;
use App\Models\Zone;
use App\Services\AlertService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ExpirePendingNodeBindingsTest extends TestCase
{
    use RefreshDatabase;

    public function test_expires_stale_pending_bind_and_clears_timestamp(): void
    {
        $this->mock(AlertService::class, function ($mock) {
            $mock->shouldReceive('createOrUpdateActive')->once()->andReturn([
                'alert' => null,
                'created' => true,
                'event_id' => null,
            ]);
        });

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);
        $node->pending_zone_set_at = now()->subHours(2);
        $node->save();

        $fresh = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);
        $fresh->pending_zone_set_at = now()->subMinutes(5);
        $fresh->save();

        $this->artisan('nodes:expire-pending-bindings', ['--ttl-minutes' => 30])
            ->assertSuccessful();

        $node->refresh();
        $fresh->refresh();

        $this->assertNull($node->pending_zone_id);
        $this->assertNull($node->pending_zone_set_at);
        $this->assertSame($zone->id, $fresh->pending_zone_id);
        $this->assertNotNull($fresh->pending_zone_set_at);
    }

    public function test_dry_run_does_not_clear_pending(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);
        $node->pending_zone_set_at = now()->subHours(3);
        $node->save();

        $this->artisan('nodes:expire-pending-bindings', [
            '--ttl-minutes' => 30,
            '--dry-run' => true,
        ])->assertSuccessful();

        $node->refresh();
        $this->assertSame($zone->id, $node->pending_zone_id);
    }

    public function test_pending_zone_set_at_is_maintained_on_model(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);

        $node->pending_zone_id = $zone->id;
        $node->save();

        $this->assertNotNull($node->fresh()->pending_zone_set_at);

        $node->pending_zone_id = null;
        $node->save();

        $this->assertNull($node->fresh()->pending_zone_set_at);
    }

    public function test_does_not_expire_when_pending_zone_set_at_is_null(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
        ]);

        // После backfill таких строк быть не должно; без якоря TTL — не expire (no updated_at fallback).
        \Illuminate\Support\Facades\DB::table('nodes')->where('id', $node->id)->update([
            'pending_zone_set_at' => null,
            'updated_at' => now()->subHours(5),
        ]);

        $this->artisan('nodes:expire-pending-bindings', ['--ttl-minutes' => 30])
            ->assertSuccessful();

        $node->refresh();
        $this->assertSame($zone->id, $node->pending_zone_id);
        $this->assertNull($node->pending_zone_set_at);
    }
}
