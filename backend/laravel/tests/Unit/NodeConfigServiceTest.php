<?php

namespace Tests\Unit;

use App\Models\DeviceNode;
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
                'type' => 'ph_node',
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
}
