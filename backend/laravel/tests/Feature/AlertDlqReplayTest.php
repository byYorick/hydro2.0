<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Support\Facades\Queue;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AlertDlqReplayTest extends TestCase
{
    use RefreshDatabase;

    public function test_replay_endpoint_requeues_from_pending_alerts_dlq(): void
    {
        Queue::fake();
        $user = User::factory()->create(['role' => 'operator']);

        $dlqId = \Illuminate\Support\Facades\DB::table('pending_alerts_dlq')->insertGetId([
            'zone_id' => null,
            'source' => 'infra',
            'code' => 'infra_test_dlq',
            'type' => 'Infrastructure Error',
            'status' => 'ACTIVE',
            'details' => json_encode(['message' => 'test']),
            'attempts' => 3,
            'max_attempts' => 3,
            'last_error' => 'boom',
            'failed_at' => now(),
            'moved_to_dlq_at' => now(),
            'original_id' => 10,
            'created_at' => now(),
        ]);

        $response = $this->actingAs($user)->postJson("/api/alerts/dlq/{$dlqId}/replay");

        $response->assertOk()
            ->assertJsonPath('status', 'ok');

        $this->assertDatabaseMissing('pending_alerts_dlq', ['id' => $dlqId]);
        $this->assertDatabaseHas('pending_alerts', [
            'code' => 'infra_test_dlq',
            'status' => 'pending',
        ]);
    }
}
