<?php

namespace Tests\Unit\Services;

use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Services\ZonePidConfigService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZonePidConfigServiceTest extends TestCase
{
    use RefreshDatabase;

    private ZonePidConfigService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = app(ZonePidConfigService::class);
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
        $payload = [
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
            'max_integral' => 20.0,
        ];
        app(AutomationConfigDocumentService::class)->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            $payload
        );

        $config = $this->service->getConfig($zone->id, 'ph');

        $this->assertNotNull($config);
        $this->assertSame(6.0, $config->config['target']);
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
            'max_integral' => 20.0,
        ];

        $result = $this->service->createOrUpdate($zone->id, 'ph', $configData, $user->id);

        $this->assertEquals($zone->id, $result->zone_id);
        $this->assertEquals('ph', $result->type);
        $this->assertEquals($user->id, $result->updated_by);
        $this->assertEquals(6.0, $result->config['target']);
        $this->assertDatabaseHas('automation_config_documents', [
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH,
            'scope_type' => AutomationConfigRegistry::SCOPE_ZONE,
            'scope_id' => $zone->id,
        ]);

        // Проверяем, что создано событие
        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'PID_CONFIG_UPDATED',
        ]);

        $event = ZoneEvent::query()
            ->where('zone_id', $zone->id)
            ->where('type', 'PID_CONFIG_UPDATED')
            ->latest('id')
            ->first();

        $this->assertNotNull($event);
        $this->assertSame('ph', $event->payload_json['type'] ?? null);
        $this->assertSame($user->id, $event->payload_json['updated_by'] ?? null);
        $this->assertEquals(6.0, $event->payload_json['new_config']['target'] ?? null);
    }

    public function test_create_or_update_updates_existing_config(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create();
        $existingConfig = [
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
            'max_integral' => 20.0,
        ];
        app(AutomationConfigDocumentService::class)->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            $existingConfig
        );

        $newConfig = [
            'target' => 6.5,
            'dead_zone' => 0.3,
            'close_zone' => 0.6,
            'far_zone' => 1.1,
            'zone_coeffs' => [
                'close' => ['kp' => 11.0, 'ki' => 0.0, 'kd' => 0.0],
                'far' => ['kp' => 13.0, 'ki' => 0.0, 'kd' => 0.0],
            ],
            'max_output' => 55.0,
            'min_interval_ms' => 65000,
            'max_integral' => 21.0,
        ];

        $result = $this->service->createOrUpdate($zone->id, 'ph', $newConfig, $user->id);

        $this->assertNull($result->id);
        $this->assertEquals(6.5, $result->config['target']);
        $this->assertEquals(0.3, $result->config['dead_zone']);
    }

    public function test_get_default_config_returns_ph_config(): void
    {
        $config = $this->service->getDefaultConfig('ph');

        $this->assertIsArray($config);
        $this->assertEquals(5.8, $config['target']);
        $this->assertEquals(0.05, $config['dead_zone']);
        $this->assertArrayHasKey('zone_coeffs', $config);
        $this->assertArrayHasKey('close', $config['zone_coeffs']);
        $this->assertArrayHasKey('far', $config['zone_coeffs']);
        $this->assertEquals(20.0, $config['max_integral']);
    }

    public function test_get_default_config_returns_ec_config(): void
    {
        $config = $this->service->getDefaultConfig('ec');

        $this->assertIsArray($config);
        $this->assertEquals(1.6, $config['target']);
        $this->assertArrayHasKey('zone_coeffs', $config);
        $this->assertEquals(100.0, $config['max_integral']);
    }

    public function test_get_default_config_prefers_system_runtime_authority_namespace(): void
    {
        $config = $this->service->getDefaultConfig('ph');
        $config['target'] = 6.2;
        $config['zone_coeffs']['close']['kp'] = 7.5;
        app(AutomationConfigDocumentService::class)->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_PID_DEFAULTS_PH,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            $config
        );

        $resolved = $this->service->getDefaultConfig('ph');

        $this->assertSame(6.2, $resolved['target']);
        $this->assertSame(7.5, $resolved['zone_coeffs']['close']['kp']);
    }

    public function test_serialize_config_returns_explicit_api_payload(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create();
        $config = $this->service->createOrUpdate($zone->id, 'ph', [
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
            'max_integral' => 20.0,
        ], $user->id);

        $payload = $this->service->serializeConfig($config);

        $this->assertSame($config->id, $payload['id']);
        $this->assertSame($zone->id, $payload['zone_id']);
        $this->assertSame('ph', $payload['type']);
        $this->assertSame($user->id, $payload['updated_by']);
        $this->assertFalse($payload['is_default']);
        $this->assertEquals(6.0, $payload['config']['target']);
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
            'target' => 15.0, // Вне диапазона для pH (4-9)
            'dead_zone' => 0.2,
            'close_zone' => 0.5,
            'far_zone' => 1.0,
            'max_integral' => 20.0,
        ];

        $this->service->validateConfig($config, 'ph');
    }

    public function test_get_all_configs_returns_all_for_zone(): void
    {
        $zone = Zone::factory()->create();
        $baseConfig = [
            'dead_zone' => 0.2,
            'close_zone' => 0.5,
            'far_zone' => 1.0,
            'zone_coeffs' => [
                'close' => ['kp' => 10.0, 'ki' => 0.0, 'kd' => 0.0],
                'far' => ['kp' => 12.0, 'ki' => 0.0, 'kd' => 0.0],
            ],
            'max_output' => 50.0,
            'min_interval_ms' => 60000,
            'max_integral' => 20.0,
        ];
        $this->service->createOrUpdate($zone->id, 'ph', ['target' => 6.0] + $baseConfig);
        $this->service->createOrUpdate($zone->id, 'ec', ['target' => 1.6] + $baseConfig);

        $configs = $this->service->getAllConfigs($zone->id);

        $this->assertCount(2, $configs);
        $this->assertArrayHasKey('ph', $configs);
        $this->assertArrayHasKey('ec', $configs);
    }
}
