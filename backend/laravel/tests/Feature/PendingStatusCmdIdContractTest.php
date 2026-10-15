<?php

namespace Tests\Feature;

use Illuminate\Database\QueryException;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class PendingStatusCmdIdContractTest extends TestCase
{
    use RefreshDatabase;

    public function test_pending_status_queues_accept_128_character_command_ids(): void
    {
        $cmdId = str_repeat('q', 128);

        DB::table('pending_status_updates')->insert([
            'cmd_id' => $cmdId,
            'status' => 'ACK',
            'retry_count' => 0,
            'max_attempts' => 10,
            'next_retry_at' => now(),
        ]);

        DB::table('pending_status_updates_dlq')->insert([
            'cmd_id' => $cmdId,
            'status' => 'DONE',
            'retry_count' => 10,
            'max_attempts' => 10,
            'last_error' => 'contract test',
        ]);

        $this->assertDatabaseHas('pending_status_updates', ['cmd_id' => $cmdId]);
        $this->assertDatabaseHas('pending_status_updates_dlq', ['cmd_id' => $cmdId]);
    }

    public function test_pending_status_queue_rejects_command_ids_over_128_characters(): void
    {
        $this->expectException(QueryException::class);

        DB::table('pending_status_updates')->insert([
            'cmd_id' => str_repeat('q', 129),
            'status' => 'ACK',
            'retry_count' => 0,
            'max_attempts' => 10,
            'next_retry_at' => now(),
        ]);
    }
}
