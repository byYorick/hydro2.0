<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Schema;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AutomationAuthoritySchemaCleanupTest extends TestCase
{
    use RefreshDatabase;

    public function test_legacy_automation_tables_are_absent_after_migrations(): void
    {
        foreach ([
            'zone_pid_configs',
            'zone_automation_logic_profiles',
            'greenhouse_automation_logic_profiles',
            'zone_process_calibrations',
            'zone_correction_configs',
            'zone_correction_config_versions',
            'grow_cycle_overrides',
            'automation_runtime_overrides',
            'system_automation_settings',
        ] as $table) {
            $this->assertFalse(Schema::hasTable($table), "Legacy table {$table} must be absent after authority cleanup.");
        }
    }
}
