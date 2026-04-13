<?php

namespace Tests\Unit;

use App\Models\AutomationEffectiveBundle;
use App\Models\DeviceNode;
use App\Models\Zone;
use App\Services\NodeConfigService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class NodeConfigServiceTest extends TestCase
{
    use RefreshDatabase;

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
                        'name' => 'main_pump',
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
                        'name' => 'main_pump',
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
        ], $config['fail_safe_guards']);
    }
}
