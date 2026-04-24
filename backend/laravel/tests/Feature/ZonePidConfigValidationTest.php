<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

class ZonePidConfigValidationTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        $user = User::factory()->create(['role' => 'admin']);
        Sanctum::actingAs($user);
    }

    public function test_validates_zone_order_dead_less_than_close(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->putJson("/api/zones/{$zone->id}/pid-configs/ph", [
            'config' => [
                'target' => 6.0,
                'dead_zone' => 0.5,
                'close_zone' => 0.3, // Меньше dead_zone - невалидно
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

        $response->assertStatus(422)
            ->assertJsonValidationErrors(['config.close_zone']);
    }

    public function test_validates_zone_order_close_less_than_far(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->putJson("/api/zones/{$zone->id}/pid-configs/ph", [
            'config' => [
                'target' => 6.0,
                'dead_zone' => 0.2,
                'close_zone' => 1.0,
                'far_zone' => 0.5, // Меньше close_zone - невалидно
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

        $response->assertStatus(422)
            ->assertJsonValidationErrors(['config.far_zone']);
    }

    public function test_validates_enable_autotune_is_required(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->putJson("/api/zones/{$zone->id}/pid-configs/ph", [
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
                // enable_autotune отсутствует
                'adaptation_rate' => 0.05,
            ],
        ]);

        $response->assertStatus(422)
            ->assertJsonValidationErrors(['config.enable_autotune']);
    }

    public function test_validates_adaptation_rate_is_required(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->putJson("/api/zones/{$zone->id}/pid-configs/ph", [
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
                // adaptation_rate отсутствует
            ],
        ]);

        $response->assertStatus(422)
            ->assertJsonValidationErrors(['config.adaptation_rate']);
    }

    public function test_accepts_valid_zone_order(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->putJson("/api/zones/{$zone->id}/pid-configs/ph", [
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

        $response->assertStatus(200);
    }
}
