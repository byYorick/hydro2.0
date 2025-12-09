<?php

namespace Tests\Unit;

use App\Console\Commands\CleanupNodeChannelsGpio;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Artisan;
use Tests\TestCase;

class CleanupNodeChannelsGpioCommandTest extends TestCase
{
    use RefreshDatabase;

    public function test_command_removes_gpio_and_pin_from_configs(): void
    {
        $node = DeviceNode::factory()->create();

        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'relay1',
            'type' => 'ACTUATOR',
            'metric' => 'RELAY',
            'unit' => null,
            'config' => [
                'gpio' => 26,
                'pin' => 1,
                'nested' => ['gpio' => 2, 'pin' => 3],
            ],
        ]);

        Artisan::call(CleanupNodeChannelsGpio::class);
        $channel->refresh();

        $this->assertArrayNotHasKey('gpio', $channel->config);
        $this->assertArrayNotHasKey('pin', $channel->config);
        $this->assertArrayHasKey('nested', $channel->config);
        $this->assertArrayNotHasKey('gpio', $channel->config['nested']);
        $this->assertArrayNotHasKey('pin', $channel->config['nested']);
    }
}
