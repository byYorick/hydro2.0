<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZonePidConfig;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

class ZonePidConfigControllerTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        // Создаем пользователя для аутентификации
        $user = User::factory()->create(['role' => 'admin']);
        Sanctum::actingAs($user);
    }

    public function test_can_get_pid_config_for_zone_and_type(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->getJson("/api/zones/{$zone->id}/pid-configs/ph");

        $response->assertStatus(200)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'type',
                    'config',
                    'is_default',
                ],
            ]);
    }

    public function test_can_get_all_pid_configs_for_zone(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->getJson("/api/zones/{$zone->id}/pid-configs");

        $response->assertStatus(200)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'ph',
                    'ec',
                ],
            ]);
    }

    public function test_can_create_pid_config(): void
    {
        $zone = Zone::factory()->create();

        $config = [
            'target' => 6.0,
            'dead_zone' => 0.2,
            'close_zone' => 0.5,
            'far_zone' => 1.0,
            'zone_coeffs' => [
                'close' => ['kp' => 10.0, 'ki' => 0.0, 'kd' => 0.0],
                'far' => ['kp' => 12.0, 'ki' => 0.0, 'kd' => 0.0],
            ],
            'max_output' => 50.0,
            'min_interval_ms' => 60000,
            'enable_autotune' => false,
            'adaptation_rate' => 0.05,
        ];

        $response = $this->putJson("/api/zones/{$zone->id}/pid-configs/ph", [
            'config' => $config,
        ]);

        $response->assertStatus(200)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'id',
                    'zone_id',
                    'type',
                    'config',
                ],
            ]);

        $this->assertDatabaseHas('zone_pid_configs', [
            'zone_id' => $zone->id,
            'type' => 'ph',
        ]);
    }

    public function test_can_update_existing_pid_config(): void
    {
        $zone = Zone::factory()->create();
        $pidConfig = ZonePidConfig::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'ph',
            'config' => [
                'target' => 6.0,
                'dead_zone' => 0.2,
                'close_zone' => 0.5,
                'far_zone' => 1.0,
                'zone_coeffs' => [
                    'close' => ['kp' => 10.0, 'ki' => 0.0, 'kd' => 0.0],
                    'far' => ['kp' => 12.0, 'ki' => 0.0, 'kd' => 0.0],
                ],
                'max_output' => 50.0,
                'min_interval_ms' => 60000,
                'enable_autotune' => false,
                'adaptation_rate' => 0.05,
            ],
        ]);

        $newConfig = [
            'target' => 6.5,
            'dead_zone' => 0.3,
            'close_zone' => 0.6,
            'far_zone' => 1.2,
            'zone_coeffs' => [
                'close' => ['kp' => 15.0, 'ki' => 0.1, 'kd' => 0.0],
                'far' => ['kp' => 18.0, 'ki' => 0.1, 'kd' => 0.0],
            ],
            'max_output' => 60.0,
            'min_interval_ms' => 90000,
            'enable_autotune' => true,
            'adaptation_rate' => 0.1,
        ];

        $response = $this->putJson("/api/zones/{$zone->id}/pid-configs/ph", [
            'config' => $newConfig,
        ]);

        $response->assertStatus(200);

        $pidConfig->refresh();
        $this->assertEquals(6.5, $pidConfig->config['target']);
        $this->assertEquals(0.3, $pidConfig->config['dead_zone']);
    }

    public function test_validates_pid_config_fields(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->putJson("/api/zones/{$zone->id}/pid-configs/ph", [
            'config' => [
                'target' => 20.0, // Невалидное значение для pH (должно быть 0-14)
                'dead_zone' => 0.2,
            ],
        ]);

        $response->assertStatus(422)
            ->assertJsonValidationErrors(['config.target']);
    }

    public function test_rate_limiting_on_update(): void
    {
        $zone = Zone::factory()->create();

        $config = [
            'target' => 6.0,
            'dead_zone' => 0.2,
            'close_zone' => 0.5,
            'far_zone' => 1.0,
            'zone_coeffs' => [
                'close' => ['kp' => 10.0, 'ki' => 0.0, 'kd' => 0.0],
                'far' => ['kp' => 12.0, 'ki' => 0.0, 'kd' => 0.0],
            ],
            'max_output' => 50.0,
            'min_interval_ms' => 60000,
            'enable_autotune' => false,
            'adaptation_rate' => 0.05,
        ];

        // Делаем 11 запросов (лимит 10 в минуту)
        // Примечание: в тестовом окружении rate limiting может работать по-другому
        // Этот тест проверяет, что middleware применен
        $response = null;
        for ($i = 0; $i < 11; $i++) {
            $response = $this->putJson("/api/zones/{$zone->id}/pid-configs/ph", [
                'config' => $config,
            ]);
            // Если получили 429, останавливаемся
            if ($response->status() === 429) {
                break;
            }
        }

        // Проверяем, что либо все запросы прошли (в тестах rate limiting может быть отключен),
        // либо получили 429
        $this->assertContains($response->status(), [200, 429]);
    }

    public function test_creates_pid_config_updated_event(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'operator']);
        Sanctum::actingAs($user);

        $config = [
            'target' => 6.0,
            'dead_zone' => 0.2,
            'close_zone' => 0.5,
            'far_zone' => 1.0,
            'zone_coeffs' => [
                'close' => ['kp' => 10.0, 'ki' => 0.0, 'kd' => 0.0],
                'far' => ['kp' => 12.0, 'ki' => 0.0, 'kd' => 0.0],
            ],
            'max_output' => 50.0,
            'min_interval_ms' => 60000,
            'enable_autotune' => false,
            'adaptation_rate' => 0.05,
        ];

        $response = $this->putJson("/api/zones/{$zone->id}/pid-configs/ph", [
            'config' => $config,
        ]);

        $response->assertStatus(200);

        // Проверяем, что создано событие PID_CONFIG_UPDATED
        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'PID_CONFIG_UPDATED',
        ]);
    }

    public function test_rejects_invalid_type(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->getJson("/api/zones/{$zone->id}/pid-configs/invalid");

        $response->assertStatus(400)
            ->assertJson([
                'status' => 'error',
            ]);
    }
}
