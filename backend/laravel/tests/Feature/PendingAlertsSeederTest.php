<?php

namespace Tests\Feature;

use Database\Seeders\ExtendedGreenhousesZonesSeeder;
use Database\Seeders\ExtendedPendingAlertsSeeder;
use Database\Seeders\PresetSeeder;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class PendingAlertsSeederTest extends TestCase
{
    use RefreshDatabase;

    public function test_extended_pending_alerts_seeder_uses_protocol_2_queue_contract(): void
    {
        $this->seed(PresetSeeder::class);
        $this->seed(ExtendedGreenhousesZonesSeeder::class);
        $this->seed(ExtendedPendingAlertsSeeder::class);

        $rows = DB::table('pending_alerts')->get();
        $this->assertGreaterThan(0, $rows->count());

        foreach ($rows as $row) {
            $this->assertContains($row->status, ['ACTIVE', 'RESOLVED']);
            $this->assertContains($row->source, ['biz', 'infra', 'node']);
            $this->assertSame(10, (int) $row->max_attempts);
            $this->assertNull($row->moved_to_dlq_at);
        }
    }
}
