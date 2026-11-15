<?php

namespace Tests\Unit;

use App\Exceptions\InvalidNodeConfigException;
use App\Models\AutomationEffectiveBundle;
use App\Models\DeviceNode;
use App\Models\Zone;
use App\Services\NodeConfigService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class NodeConfigServiceTest extends TestCase
{
    use RefreshDatabase;

    private string $originalEnv;

    protected function setUp(): void
    {
        parent::setUp();
        $this->originalEnv = (string) $this->app['env'];
    }

    protected function tearDown(): void
    {
        $this->app['env'] = $this->originalEnv;
        parent::tearDown();
    }

    public function test_get_stored_config_sanitizes_credentials_and_gpio(): void
    {
        $node = DeviceNode::factory()->create([
            'config' => [
                'node_id' => 'nd-ph-1',
                'version' => 3,
                'type' => 'ph',
                'wifi' => [
                    'ssid' => 'HydroFarm',
                    'pass' => 'super-secret',
                ],
                'mqtt' => [
                    'host' => 'mqtt',
                    'port' => 1883,
                    'password' => 'super-secret',
                ],
                'channels' => [
                    [
                        'name' => 'pump_acid',
                        'type' => 'ACTUATOR',
                        'gpio' => 26,
                        'safe_limits' => [
                            'max_duration_ms' => 1000,
                            'min_off_ms' => 2000,
                            'fail_safe_mode' => 'NC',
                        ],
                    ],
                ],
            ],
        ]);

        /** @var NodeConfigService $service */
        $service = $this->app->make(NodeConfigService::class);
        $config = $service->getStoredConfig($node, false);

        $this->assertSame(['configured' => true], $config['wifi']);
        $this->assertSame(['configured' => true], $config['mqtt']);
        $this->assertArrayHasKey('channels', $config);
        $this->assertSame('pump_acid', $config['channels'][0]['name']);
        $this->assertArrayNotHasKey('gpio', $config['channels'][0]);
        $this->assertSame('NC', $config['channels'][0]['safe_limits']['fail_safe_mode']);
    }

    public function test_generate_node_config_includes_credentials_and_strips_gpio(): void
    {
        $node = DeviceNode::factory()->create([
            'config' => [
                'node_id' => 'nd-ph-1',
                'version' => 3,
                'type' => 'ph',
                'wifi' => [
                    'ssid' => 'HydroFarm',
                    'pass' => 'super-secret',
                ],
                'mqtt' => [
                    'host' => 'mqtt',
                    'port' => 1883,
                    'password' => 'super-secret',
                ],
                'channels' => [
                    [
                        'name' => 'pump_acid',
                        'type' => 'ACTUATOR',
                        'gpio' => 26,
                        'safe_limits' => [
                            'max_duration_ms' => 1000,
                            'min_off_ms' => 2000,
                            'fail_safe_mode' => 'NC',
                        ],
                    ],
                ],
            ],
        ]);

        /** @var NodeConfigService $service */
        $service = $this->app->make(NodeConfigService::class);
        $config = $service->generateNodeConfig($node, null, true, false);

        $this->assertSame('HydroFarm', $config['wifi']['ssid']);
        $this->assertSame('super-secret', $config['wifi']['pass']);
        $this->assertSame('mqtt', $config['mqtt']['host']);
        $this->assertArrayNotHasKey('gpio', $config['channels'][0]);
    }

    public function test_generate_node_config_sets_default_relay_type_for_relay_actuator(): void
    {
        $node = DeviceNode::factory()->create([
            'config' => [
                'node_id' => 'nd-irrig-1',
                'version' => 1,
                'type' => 'irrig',
                'channels' => [
                    [
                        'name' => 'pump_main',
                        'type' => 'ACTUATOR',
                        'actuator_type' => 'RELAY',
                    ],
                ],
            ],
        ]);

        /** @var NodeConfigService $service */
        $service = $this->app->make(NodeConfigService::class);
        $config = $service->generateNodeConfig($node, null, true, false);

        $this->assertSame('NO', $config['channels'][0]['relay_type']);
    }

    public function test_generate_node_config_keeps_valid_relay_type(): void
    {
        $node = DeviceNode::factory()->create([
            'config' => [
                'node_id' => 'nd-irrig-1',
                'version' => 1,
                'type' => 'irrig',
                'channels' => [
                    [
                        'name' => 'pump_main',
                        'type' => 'ACTUATOR',
                        'actuator_type' => 'VALVE',
                        'relay_type' => 'NC',
                    ],
                ],
            ],
        ]);

        /** @var NodeConfigService $service */
        $service = $this->app->make(NodeConfigService::class);
        $config = $service->generateNodeConfig($node, null, true, false);

        $this->assertSame('NC', $config['channels'][0]['relay_type']);
    }

    public function test_generate_node_config_mirrors_fail_safe_guards_from_zone_logic_profile_bundle(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'irrig',
            'config' => [
                'node_id' => 'nd-irrig-1',
                'version' => 1,
                'type' => 'irrig',
                'channels' => [],
            ],
        ]);

        // Bootstrap-материализация при создании зоны уже могла создать запись
        // с (scope_type=zone, scope_id=$zone->id) — перезаписываем её тестовой
        // конфигурацией с нужными fail_safe_guards.
        AutomationEffectiveBundle::query()->updateOrCreate([
            'scope_type' => 'zone',
            'scope_id' => $zone->id,
        ], [
            'bundle_revision' => 'test-rev',
            'schema_revision' => '1',
            'status' => 'valid',
            'inputs_checksum' => 'test-checksum',
            'compiled_at' => now(),
            'config' => [
                'zone' => [
                    'logic_profile' => [
                        'active_mode' => 'working',
                        'active_profile' => [
                            'subsystems' => [
                                'diagnostics' => [
                                    'execution' => [
                                        'fail_safe_guards' => [
                                            'clean_fill_min_check_delay_ms' => 9000,
                                            'solution_fill_clean_min_check_delay_ms' => 11000,
                                            'solution_fill_solution_min_check_delay_ms' => 17000,
                                            'recirculation_stop_on_solution_min' => false,
                                            'irrigation_stop_on_solution_min' => true,
                                            'estop_debounce_ms' => 120,
                                        ],
                                    ],
                                ],
                            ],
                        ],
                    ],
                ],
            ],
        ]);

        /** @var NodeConfigService $service */
        $service = $this->app->make(NodeConfigService::class);
        $config = $service->generateNodeConfig($node, null, true, false);

        $this->assertSame([
            'clean_fill_min_check_delay_ms' => 9000,
            'solution_fill_clean_min_check_delay_ms' => 11000,
            'solution_fill_solution_min_check_delay_ms' => 17000,
            'recirculation_solution_min_guard_enabled' => false,
            'irrigation_solution_min_guard_enabled' => true,
            'estop_debounce_ms' => 120,
            'link_loss_timeout_sec' => 30,
        ], $config['fail_safe_guards']);
        $this->assertSame(30, $config['link_loss_timeout_sec']);
    }

    public function test_generate_node_config_sets_default_link_loss_timeout_for_ph_node(): void
    {
        $node = DeviceNode::factory()->create([
            'type' => 'ph',
            'config' => [
                'node_id' => 'nd-ph-1',
                'version' => 3,
                'type' => 'ph',
                'channels' => [],
            ],
        ]);

        $config = $this->app->make(NodeConfigService::class)->generateNodeConfig($node, null, true, false);

        $this->assertSame(30, $config['link_loss_timeout_sec']);
    }

    public function test_generate_node_config_does_not_fallback_to_app_key_in_production(): void
    {
        $this->app['env'] = 'production';
        config(['app.node_default_secret' => null, 'app.key' => 'base64:prod-app-key-should-not-leak']);

        $node = new DeviceNode([
            'id' => 99,
            'uid' => 'nd-ph-no-secret',
            'type' => 'ph',
            'config' => [
                'node_id' => 'nd-ph-no-secret',
                'version' => 3,
                'type' => 'ph',
                'channels' => [],
            ],
        ]);

        /** @var NodeConfigService $service */
        $service = $this->app->make(NodeConfigService::class);
        $config = $service->generateNodeConfig($node, null, true, false);

        $this->assertArrayNotHasKey('node_secret', $config);
    }

    public function test_generate_node_config_includes_per_node_secret(): void
    {
        $secret = bin2hex(random_bytes(32));
        $node = new DeviceNode([
            'id' => 100,
            'uid' => 'nd-ph-with-secret',
            'type' => 'ph',
            'config' => [
                'node_id' => 'nd-ph-with-secret',
                'version' => 3,
                'type' => 'ph',
                'node_secret' => $secret,
                'channels' => [],
            ],
        ]);

        /** @var NodeConfigService $service */
        $service = $this->app->make(NodeConfigService::class);
        $config = $service->generateNodeConfig($node, null, true, false);

        $this->assertSame($secret, $config['node_secret']);
    }

    public function test_link_loss_timeout_accepts_bounds_and_defaults_when_absent(): void
    {
        foreach ([10, 30, 300] as $timeout) {
            $node = DeviceNode::factory()->create([
                'type' => 'ph',
                'config' => [
                    'node_id' => 'nd-ph-timeout',
                    'version' => 3,
                    'type' => 'ph',
                    'link_loss_timeout_sec' => $timeout,
                    'channels' => [],
                ],
            ]);

            $config = $this->app->make(NodeConfigService::class)->generateNodeConfig($node, null, true, false);

            $this->assertSame($timeout, $config['link_loss_timeout_sec']);
        }
    }

    public function test_link_loss_timeout_rejects_zero_and_out_of_range_without_clamp(): void
    {
        foreach ([0, 9, 301] as $timeout) {
            $node = new DeviceNode([
                'uid' => 'nd-ph-bad-timeout',
                'type' => 'ph',
                'config' => [
                    'node_id' => 'nd-ph-bad-timeout',
                    'version' => 3,
                    'type' => 'ph',
                    'link_loss_timeout_sec' => $timeout,
                    'channels' => [],
                ],
            ]);

            try {
                $this->app->make(NodeConfigService::class)->generateNodeConfig($node, null, true, false);
                $this->fail("link_loss_timeout_sec {$timeout} must reject the config");
            } catch (InvalidNodeConfigException $e) {
                $this->assertStringContainsString('10 to 300', $e->getMessage());
            }
        }
    }

    public function test_link_loss_timeout_rejects_non_integer(): void
    {
        $node = new DeviceNode([
            'uid' => 'nd-ph-fraction',
            'type' => 'ph',
            'config' => [
                'node_id' => 'nd-ph-fraction',
                'version' => 3,
                'type' => 'ph',
                'link_loss_timeout_sec' => 30.5,
                'channels' => [],
            ],
        ]);

        $this->expectException(InvalidNodeConfigException::class);
        $this->app->make(NodeConfigService::class)->generateNodeConfig($node, null, true, false);
    }

    public function test_irrigation_profile_link_loss_timeout_rejects_zero_and_accepts_bounds(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'irrig',
            'config' => [
                'node_id' => 'nd-irrig-1',
                'version' => 3,
                'type' => 'irrig',
                'channels' => [],
            ],
        ]);

        $this->storeIrrigationLinkLoss($zone, 0);

        try {
            $this->app->make(NodeConfigService::class)->generateNodeConfig($node, null, true, false);
            $this->fail('profile link_loss_timeout_sec 0 must reject the config');
        } catch (InvalidNodeConfigException) {
            $this->assertTrue(true);
        }

        foreach ([10, 30, 300] as $timeout) {
            $this->storeIrrigationLinkLoss($zone, $timeout);
            $config = $this->app->make(NodeConfigService::class)->generateNodeConfig($node, null, true, false);
            $this->assertSame($timeout, $config['link_loss_timeout_sec']);
            $this->assertSame($timeout, $config['fail_safe_guards']['link_loss_timeout_sec']);
        }
    }

    public function test_stored_guard_link_loss_zero_rejects_even_when_top_level_is_valid(): void
    {
        $node = new DeviceNode([
            'uid' => 'nd-ph-guard-zero',
            'type' => 'ph',
            'config' => [
                'node_id' => 'nd-ph-guard-zero',
                'version' => 3,
                'type' => 'ph',
                'link_loss_timeout_sec' => 30,
                'fail_safe_guards' => [
                    'link_loss_timeout_sec' => 0,
                ],
                'channels' => [],
            ],
        ]);

        $this->expectException(InvalidNodeConfigException::class);
        $this->app->make(NodeConfigService::class)->generateNodeConfig($node, null, true, false);
    }

    private function storeIrrigationLinkLoss(Zone $zone, int $timeout): void
    {
        AutomationEffectiveBundle::query()->updateOrCreate([
            'scope_type' => 'zone',
            'scope_id' => $zone->id,
        ], [
            'bundle_revision' => 'test-rev',
            'schema_revision' => '1',
            'status' => 'valid',
            'inputs_checksum' => 'test-checksum',
            'compiled_at' => now(),
            'config' => [
                'zone' => [
                    'logic_profile' => [
                        'active_mode' => 'working',
                        'active_profile' => [
                            'subsystems' => [
                                'diagnostics' => [
                                    'execution' => [
                                        'fail_safe_guards' => [
                                            'link_loss_timeout_sec' => $timeout,
                                        ],
                                    ],
                                ],
                            ],
                        ],
                    ],
                ],
            ],
        ]);
    }
}
