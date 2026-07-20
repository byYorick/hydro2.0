<?php

namespace Tests\Feature;

use App\Enums\NodeLifecycleState;
use App\Jobs\PublishNodeConfigJob;
use App\Models\DeviceNode;
use App\Models\Zone;
use Illuminate\Support\Facades\Queue;
use Tests\RefreshDatabase;
use Tests\TestCase;

class EnsureNodeSecretsCommandTest extends TestCase
{
    use RefreshDatabase;

    public function test_backfills_missing_secrets_and_queues_republish_for_assigned_nodes(): void
    {
        Queue::fake([PublishNodeConfigJob::class]);

        $zone = Zone::factory()->create();
        $assigned = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
            'config' => ['version' => 3],
        ]);
        $unassigned = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => null,
            'lifecycle_state' => NodeLifecycleState::REGISTERED_BACKEND,
            'config' => [],
        ]);
        $existingSecret = str_repeat('ef', 32);
        $alreadyHas = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'config' => ['node_secret' => $existingSecret],
        ]);

        $this->artisan('nodes:ensure-secrets')
            ->assertSuccessful();

        $assigned->refresh();
        $unassigned->refresh();
        $alreadyHas->refresh();

        $assignedSecret = $assigned->config['node_secret'] ?? null;
        $unassignedSecret = $unassigned->config['node_secret'] ?? null;

        $this->assertIsString($assignedSecret);
        $this->assertSame(64, strlen($assignedSecret));
        $this->assertIsString($unassignedSecret);
        $this->assertSame(64, strlen($unassignedSecret));
        $this->assertSame($existingSecret, $alreadyHas->config['node_secret']);

        Queue::assertPushed(PublishNodeConfigJob::class, function (PublishNodeConfigJob $job) use ($assigned) {
            return $job->nodeId === $assigned->id;
        });
        Queue::assertNotPushed(PublishNodeConfigJob::class, function (PublishNodeConfigJob $job) use ($unassigned) {
            return $job->nodeId === $unassigned->id;
        });
        Queue::assertNotPushed(PublishNodeConfigJob::class, function (PublishNodeConfigJob $job) use ($alreadyHas) {
            return $job->nodeId === $alreadyHas->id;
        });
    }

    public function test_command_is_idempotent(): void
    {
        Queue::fake([PublishNodeConfigJob::class]);

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'config' => [],
        ]);

        $this->artisan('nodes:ensure-secrets')->assertSuccessful();
        $node->refresh();
        $firstSecret = $node->config['node_secret'] ?? null;
        $this->assertIsString($firstSecret);

        Queue::fake([PublishNodeConfigJob::class]);
        $this->artisan('nodes:ensure-secrets')
            ->expectsOutputToContain('All nodes already have node_secret')
            ->assertSuccessful();

        $node->refresh();
        $this->assertSame($firstSecret, $node->config['node_secret']);
        Queue::assertNothingPushed();
    }

    public function test_dry_run_does_not_write_or_republish(): void
    {
        Queue::fake([PublishNodeConfigJob::class]);

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'config' => [],
        ]);

        $this->artisan('nodes:ensure-secrets', ['--dry-run' => true])
            ->assertSuccessful();

        $node->refresh();
        $this->assertArrayNotHasKey('node_secret', $node->config ?? []);
        Queue::assertNothingPushed();
    }

    public function test_no_republish_skips_config_job(): void
    {
        Queue::fake([PublishNodeConfigJob::class]);

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'config' => [],
        ]);

        $this->artisan('nodes:ensure-secrets', ['--no-republish' => true])
            ->assertSuccessful();

        $node->refresh();
        $this->assertIsString($node->config['node_secret'] ?? null);
        Queue::assertNothingPushed();
    }
}
