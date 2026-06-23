<?php

namespace Tests\Unit\Services;

use App\Models\Command;
use App\Models\DeviceNode;
use App\Models\Zone;
use App\Services\CommandTimeoutDiagnosticsBuilder;
use Tests\RefreshDatabase;
use Tests\TestCase;

class CommandTimeoutDiagnosticsBuilderTest extends TestCase
{
    use RefreshDatabase;

    public function test_builds_timeout_payload_from_command_and_node(): void
    {
        config(['commands.timeout_minutes' => 7]);

        $zone = Zone::factory()->create();
        $node = DeviceNode::query()->create([
            'zone_id' => $zone->id,
            'uid' => 'nd-timeout-builder',
            'type' => 'irrig',
            'status' => 'online',
            'last_seen_at' => now()->subMinutes(4),
        ]);
        $command = Command::withoutEvents(fn () => Command::create([
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'cmd_id' => 'cmd-timeout-builder',
            'status' => Command::STATUS_ACK,
            'cmd' => 'run_pump',
            'channel' => 'pump_main',
            'sent_at' => now()->subMinutes(10),
        ]));

        $payload = app(CommandTimeoutDiagnosticsBuilder::class)->fromCommand($command);

        $this->assertSame('nd-timeout-builder', $payload['node_uid']);
        $this->assertSame('pump_main', $payload['channel']);
        $this->assertSame(7, $payload['timeout_minutes']);
        $this->assertSame('online', $payload['node_status']);
    }
}
