<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        foreach ([
            'zone_correction_config_versions',
            'zone_correction_configs',
            'zone_pid_configs',
            'zone_automation_logic_profiles',
            'greenhouse_automation_logic_profiles',
            'zone_process_calibrations',
            'grow_cycle_overrides',
            'automation_runtime_overrides',
            'system_automation_settings',
        ] as $table) {
            Schema::dropIfExists($table);
        }
    }

    public function down(): void
    {
        // Breaking cleanup: legacy automation stack is intentionally not restored.
    }
};
