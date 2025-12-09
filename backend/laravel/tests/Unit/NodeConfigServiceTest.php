<?php

namespace Tests\Unit;

use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Services\NodeConfigService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class NodeConfigServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_generate_config_does_not_include_channels(): void
    {
        $zone = \App\Models\Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'relay',
        ]);

        NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'relay1',
            'type' => 'ACTUATOR',
            'metric' => 'RELAY',
            'unit' => null,
            'config' => [
                'gpio' => 26,
                'pin' => 99,
                'safe_limits' => [
                    'max_duration_ms' => 1000,
                    'min_off_ms' => 2000,
                ],
            ],
        ]);

        /** @var NodeConfigService $service */
        $service = $this->app->make(NodeConfigService::class);
        $config = $service->generateNodeConfig($node, null, false);

        $this->assertArrayHasKey('channels', $config);
        $this->assertSame([], $config['channels'], 'Сервер не должен отправлять каналы на ноду');
    }
}
