<?php

namespace Tests\Unit\Models;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZonePidConfig;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ZonePidConfigTest extends TestCase
{
    use RefreshDatabase;

    public function test_zone_pid_config_belongs_to_zone(): void
    {
        $zone = Zone::factory()->create();
        $pidConfig = ZonePidConfig::factory()->create([
            'zone_id' => $zone->id,
        ]);

        $this->assertInstanceOf(Zone::class, $pidConfig->zone);
        $this->assertEquals($zone->id, $pidConfig->zone->id);
    }

    public function test_zone_pid_config_belongs_to_user(): void
    {
        $user = User::factory()->create();
        $pidConfig = ZonePidConfig::factory()->create([
            'updated_by' => $user->id,
        ]);

        $this->assertInstanceOf(User::class, $pidConfig->updatedBy);
        $this->assertEquals($user->id, $pidConfig->updatedBy->id);
    }

    public function test_zone_pid_config_accessors(): void
    {
        $config = [
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

        $pidConfig = ZonePidConfig::factory()->create([
            'config' => $config,
        ]);

        $this->assertEquals(6.5, $pidConfig->target);
        $this->assertEquals(0.3, $pidConfig->dead_zone);
        $this->assertEquals(0.6, $pidConfig->close_zone);
        $this->assertEquals(1.2, $pidConfig->far_zone);
        $this->assertEquals(60.0, $pidConfig->max_output);
        $this->assertEquals(90000, $pidConfig->min_interval_ms);
        $this->assertTrue($pidConfig->enable_autotune);
        $this->assertEquals(0.1, $pidConfig->adaptation_rate);

        $this->assertIsArray($pidConfig->close_coeffs);
        $this->assertEquals(15.0, $pidConfig->close_coeffs['kp']);
        $this->assertIsArray($pidConfig->far_coeffs);
        $this->assertEquals(18.0, $pidConfig->far_coeffs['kp']);
    }

    public function test_zone_has_pid_configs_relationship(): void
    {
        $zone = Zone::factory()->create();
        ZonePidConfig::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'ph',
        ]);
        ZonePidConfig::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'ec',
        ]);

        $this->assertCount(2, $zone->pidConfigs);
    }
}
