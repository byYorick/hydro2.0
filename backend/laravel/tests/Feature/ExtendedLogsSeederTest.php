<?php

namespace Tests\Feature;

use Database\Seeders\ExtendedGreenhousesZonesSeeder;
use Database\Seeders\ExtendedLogsSeeder;
use Database\Seeders\ExtendedNodesChannelsSeeder;
use Database\Seeders\PresetSeeder;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ExtendedLogsSeederTest extends TestCase
{
    use RefreshDatabase;

    public function test_extended_logs_seeder_uses_scheduler_task_lifecycle_contract(): void
    {
        $this->seed(PresetSeeder::class);
        $this->seed(ExtendedGreenhousesZonesSeeder::class);
        $this->seed(ExtendedNodesChannelsSeeder::class);
        $this->seed(ExtendedLogsSeeder::class);

        $schedulerLogs = DB::table('scheduler_logs')->get();
        $contractLogs = $schedulerLogs->filter(function ($log): bool {
            $details = json_decode((string) $log->details, true);
            return is_array($details) && ($details['contract_version'] ?? null) === 'scheduler_task_v2';
        });
        $this->assertGreaterThan(0, $contractLogs->count());

        $allowedStatuses = [
            'accepted',
            'running',
            'completed',
            'failed',
            'rejected',
            'expired',
            'timeout',
            'not_found',
        ];

        foreach ($contractLogs as $log) {
            $this->assertContains($log->status, $allowedStatuses);

            $details = json_decode((string) $log->details, true);
            $this->assertIsArray($details);
            $this->assertArrayHasKey('task_id', $details);
            $this->assertArrayHasKey('zone_id', $details);
            $this->assertArrayHasKey('task_type', $details);
            $this->assertArrayHasKey('status', $details);
            $this->assertArrayHasKey('correlation_id', $details);
            $this->assertArrayHasKey('scheduled_for', $details);
            $this->assertArrayHasKey('due_at', $details);
            $this->assertArrayHasKey('expires_at', $details);
        }
    }
}
