<?php

namespace Tests\Feature;

use App\Models\Command;
use App\Models\Zone;
use Illuminate\Support\Facades\Config;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ProcessCommandTimeoutsTest extends TestCase
{
    use RefreshDatabase;

    public function test_process_timeouts_marks_ack_command_as_timeout_with_terminal_metadata(): void
    {
        Config::set('commands.timeout_minutes', 5);

        $zone = Zone::factory()->create();
        $command = Command::create([
            'zone_id' => $zone->id,
            'cmd_id' => 'cmd-ack-timeout-001',
            'status' => Command::STATUS_ACK,
            'cmd' => 'test_command',
            'sent_at' => now()->subMinutes(10),
            'ack_at' => now()->subMinutes(9),
        ]);

        $this->artisan('commands:process-timeouts')
            ->assertExitCode(0);

        $command->refresh();
        $this->assertEquals(Command::STATUS_TIMEOUT, $command->status);
        $this->assertNotNull($command->failed_at);
        $this->assertEquals('TIMEOUT', $command->error_code);
        $this->assertEquals(1, $command->result_code);

        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'COMMAND_TIMEOUT',
        ]);
    }

    public function test_process_timeouts_does_not_touch_recent_ack_command(): void
    {
        Config::set('commands.timeout_minutes', 5);

        $zone = Zone::factory()->create();
        $command = Command::create([
            'zone_id' => $zone->id,
            'cmd_id' => 'cmd-ack-recent-001',
            'status' => Command::STATUS_ACK,
            'cmd' => 'test_command',
            'sent_at' => now()->subMinutes(2),
            'ack_at' => now()->subMinute(),
        ]);

        $this->artisan('commands:process-timeouts')
            ->assertExitCode(0);

        $command->refresh();
        $this->assertEquals(Command::STATUS_ACK, $command->status);
        $this->assertNull($command->failed_at);

        $this->assertDatabaseMissing('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'COMMAND_TIMEOUT',
        ]);
    }
}
