<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class UnassignedNodeErrorApiTest extends TestCase
{
    use RefreshDatabase;

    public function test_global_unassigned_errors_api_returns_severity_and_human_message(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $now = now();

        DB::table('unassigned_node_errors')->insert([
            'hardware_id' => 'esp32-global-api',
            'error_message' => 'Pump is already running',
            'error_code' => 'pump_busy',
            'severity' => 'ERROR',
            'topic' => 'hydro/gh/zn/esp32-global-api/error',
            'last_payload' => json_encode(['detail' => 'busy']),
            'count' => 2,
            'first_seen_at' => $now,
            'last_seen_at' => $now,
            'created_at' => $now,
            'updated_at' => $now,
        ]);

        $response = $this->actingAs($user)
            ->getJson('/api/unassigned-node-errors');

        $response->assertOk()
            ->assertJsonPath('data.0.hardware_id', 'esp32-global-api')
            ->assertJsonPath('data.0.severity', 'ERROR')
            ->assertJsonPath('data.0.error_code', 'pump_busy');

        $humanMessage = $response->json('data.0.human_error_message');
        $this->assertIsString($humanMessage);
        $this->assertStringContainsString('занят', mb_strtolower($humanMessage));
    }
}
