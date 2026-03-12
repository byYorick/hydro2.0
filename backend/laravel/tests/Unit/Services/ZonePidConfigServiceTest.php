<?php

namespace Tests\Unit\Services;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZonePidConfig;
use App\Services\ZonePidConfigService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ZonePidConfigServiceTest extends TestCase
{
    use RefreshDatabase;

    private ZonePidConfigService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = new ZonePidConfigService;
    }

    public function test_get_config_returns_null_when_not_exists(): void
    {
        $zone = Zone::factory()->create();

        $config = $this->service->getConfig($zone->id, 'ph');

        $this->assertNull($config);
    }

    public function test_get_config_returns_existing_config(): void
    {
        $zone = Zone::factory()->create();
        $pidConfig = ZonePidConfig::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'ph',
        ]);

        $config = $this->service->getConfig($zone->id, 'ph');

        $this->assertNotNull($config);
        $this->assertEquals($pidConfig->id, $config->id);
    }

    public function test_create_or_update_creates_new_config(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create();

        $configData = [
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

        $result = $this->service->createOrUpdate($zone->id, 'ph', $configData, $user->id);

        $this->assertInstanceOf(ZonePidConfig::class, $result);
        $this->assertEquals($zone->id, $result->zone_id);
        $this->assertEquals('ph', $result->type);
        $this->assertEquals($user->id, $result->updated_by);
        $this->assertEquals(6.0, $result->config['target']);

        // Проверяем, что создано событие
        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'PID_CONFIG_UPDATED',
        ]);
    }

    public function test_create_or_update_updates_existing_config(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create();
        $pidConfig = ZonePidConfig::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'ph',
            'config' => ['target' => 6.0],
        ]);

        $newConfig = ['target' => 6.5, 'dead_zone' => 0.3];

        $result = $this->service->createOrUpdate($zone->id, 'ph', $newConfig, $user->id);

        $this->assertEquals($pidConfig->id, $result->id);
        $pidConfig->refresh();
        $this->assertEquals(6.5, $pidConfig->config['target']);
        $this->assertEquals(0.3, $pidConfig->config['dead_zone']);
    }

    public function test_get_default_config_returns_ph_config(): void
    {
        $config = $this->service->getDefaultConfig('ph');

        $this->assertIsArray($config);
        $this->assertEquals(6.0, $config['target']);
        $this->assertEquals(0.2, $config['dead_zone']);
        $this->assertArrayHasKey('zone_coeffs', $config);
        $this->assertArrayHasKey('close', $config['zone_coeffs']);
        $this->assertArrayHasKey('far', $config['zone_coeffs']);
    }

    public function test_get_default_config_returns_ec_config(): void
    {
        $config = $this->service->getDefaultConfig('ec');

        $this->assertIsArray($config);
        $this->assertEquals(2.0, $config['target']);
        $this->assertArrayHasKey('zone_coeffs', $config);
    }

    public function test_validate_config_throws_exception_for_invalid_zones(): void
    {
        $this->expectException(\InvalidArgumentException::class);

        $config = [
            'dead_zone' => 0.5,
            'close_zone' => 0.3, // Меньше dead_zone - невалидно
            'far_zone' => 1.0,
        ];

        $this->service->validateConfig($config, 'ph');
    }

    public function test_validate_config_throws_exception_for_invalid_ph_target(): void
    {
        $this->expectException(\InvalidArgumentException::class);

        $config = [
            'target' => 15.0, // Вне диапазона для pH
            'dead_zone' => 0.2,
            'close_zone' => 0.5,
            'far_zone' => 1.0,
        ];

        $this->service->validateConfig($config, 'ph');
    }

    public function test_get_all_configs_returns_all_for_zone(): void
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

        $configs = $this->service->getAllConfigs($zone->id);

        $this->assertCount(2, $configs);
        $this->assertArrayHasKey('ph', $configs);
        $this->assertArrayHasKey('ec', $configs);
    }
}
