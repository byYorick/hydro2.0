<?php

namespace Tests\Feature;

use App\Models\ChannelBinding;
use App\Models\InfrastructureInstance;
use App\Models\Zone;
use Database\Seeders\FullServiceTestSeeder;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class FullServiceTestSeederTest extends TestCase
{
    use RefreshDatabase;

    public function test_full_service_seeder_creates_infrastructure_and_capabilities(): void
    {
        $this->seed(FullServiceTestSeeder::class);

        $this->assertGreaterThan(0, InfrastructureInstance::count());
        $this->assertGreaterThan(0, ChannelBinding::count());

        $zones = Zone::all();
        $this->assertNotEmpty($zones);

        $hasAutomationCapabilities = $zones->contains(function (Zone $zone): bool {
            $capabilities = $zone->capabilities ?? [];

            return ! empty($capabilities['irrigation_control'])
                || ! empty($capabilities['light_control'])
                || ! empty($capabilities['climate_control']);
        });

        $this->assertTrue($hasAutomationCapabilities);

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
        $terminalStatuses = ['completed', 'failed', 'rejected', 'expired', 'timeout', 'not_found'];

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

            if (in_array($log->status, $terminalStatuses, true)) {
                $this->assertArrayHasKey('result', $details);
                $this->assertIsArray($details['result']);
                $this->assertArrayHasKey('action_required', $details['result']);
                $this->assertArrayHasKey('decision', $details['result']);
                $this->assertArrayHasKey('reason_code', $details['result']);
                $this->assertArrayHasKey('error_code', $details['result']);
            }
        }
    }
}
