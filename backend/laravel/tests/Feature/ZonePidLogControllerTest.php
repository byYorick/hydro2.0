<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneEvent;
use Tests\RefreshDatabase;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

class ZonePidLogControllerTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        $user = User::factory()->create(['role' => 'admin']);
        Sanctum::actingAs($user);
    }

    public function test_can_get_pid_logs(): void
    {
        $zone = Zone::factory()->create();

        // Создаем события PID_OUTPUT
        ZoneEvent::create([
            'zone_id' => $zone->id,
            'type' => 'PID_OUTPUT',
            'details' => [
                'type' => 'ph',
                'zone_state' => 'close',
                'output' => 5.5,
                'error' => 0.3,
                'current' => 6.3,
                'target' => 6.0,
            ],
        ]);

        $response = $this->getJson("/api/zones/{$zone->id}/pid-logs");

        $response->assertStatus(200)
            ->assertJsonStructure([
                'status',
                'data' => [
                    '*' => [
                        'id',
                        'type',
                        'created_at',
                    ],
                ],
                'meta',
            ]);
    }

    public function test_can_filter_pid_logs_by_type(): void
    {
        $zone = Zone::factory()->create();

        ZoneEvent::create([
            'zone_id' => $zone->id,
            'type' => 'PID_OUTPUT',
            'details' => ['type' => 'ph', 'output' => 5.5],
        ]);

        ZoneEvent::create([
            'zone_id' => $zone->id,
            'type' => 'PID_OUTPUT',
            'details' => ['type' => 'ec', 'output' => 10.0],
        ]);

        $response = $this->getJson("/api/zones/{$zone->id}/pid-logs?type=ph");

        $response->assertStatus(200);
        $data = $response->json('data');
        $this->assertNotEmpty($data);
        // Все логи должны быть типа ph
        foreach ($data as $log) {
            if ($log['type'] !== 'config_updated') {
                $this->assertEquals('ph', $log['type']);
            }
        }
    }

    public function test_pid_logs_supports_pagination(): void
    {
        $zone = Zone::factory()->create();

        // Создаем несколько событий
        for ($i = 0; $i < 5; $i++) {
            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'PID_OUTPUT',
                'details' => [
                    'type' => 'ph',
                    'output' => 5.5 + $i,
                ],
            ]);
        }

        $response = $this->getJson("/api/zones/{$zone->id}/pid-logs?limit=2&offset=0");

        $response->assertStatus(200);
        $data = $response->json('data');
        $this->assertLessThanOrEqual(2, count($data));
    }

    public function test_pid_logs_read_canonical_payload_json_for_output_and_config_updates(): void
    {
        $zone = Zone::factory()->create();

        ZoneEvent::create([
            'zone_id' => $zone->id,
            'type' => 'PID_OUTPUT',
            'payload_json' => [
                'type' => 'ph',
                'zone_state' => 'far',
                'output' => 9.5,
                'error' => 0.42,
                'integral_term' => 1.75,
                'current' => 6.22,
                'target' => 5.8,
                'dt_seconds' => 2.0,
            ],
        ]);

        ZoneEvent::create([
            'zone_id' => $zone->id,
            'type' => 'PID_CONFIG_UPDATED',
            'payload_json' => [
                'type' => 'ph',
                'updated_by' => 77,
                'new_config' => [
                    'target' => 5.8,
                    'max_output' => 20.0,
                    'min_interval_ms' => 90000,
                ],
                'old_config' => [
                    'target' => 6.0,
                ],
            ],
        ]);

        $response = $this->getJson("/api/zones/{$zone->id}/pid-logs?type=ph");

        $response->assertStatus(200)
            ->assertJsonPath('data.0.type', 'config_updated')
            ->assertJsonPath('data.0.pid_type', 'ph')
            ->assertJsonPath('data.0.updated_by', 77)
            ->assertJsonPath('data.0.new_config.target', 5.8)
            ->assertJsonPath('data.1.type', 'ph')
            ->assertJsonPath('data.1.integral_term', 1.75)
            ->assertJsonPath('data.1.zone_state', 'far');
    }
}
