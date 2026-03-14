<?php

use App\Services\SystemAutomationSettingsCatalog;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        $defaults = json_encode(
            SystemAutomationSettingsCatalog::defaults('pump_calibration'),
            JSON_THROW_ON_ERROR
        );

        DB::statement(
            "UPDATE zone_correction_configs
             SET resolved_config = jsonb_set(
                 COALESCE(resolved_config, '{}'::jsonb),
                 '{pump_calibration}',
                 ?::jsonb,
                 true
             )
             WHERE resolved_config IS NULL
                OR jsonb_typeof(resolved_config) <> 'object'
                OR NOT jsonb_exists(resolved_config, 'pump_calibration')",
            [$defaults]
        );

        DB::statement(
            "UPDATE zone_correction_config_versions
             SET resolved_config = jsonb_set(
                 COALESCE(resolved_config, '{}'::jsonb),
                 '{pump_calibration}',
                 ?::jsonb,
                 true
             )
             WHERE resolved_config IS NULL
                OR jsonb_typeof(resolved_config) <> 'object'
                OR NOT jsonb_exists(resolved_config, 'pump_calibration')",
            [$defaults]
        );
    }

    public function down(): void
    {
        DB::statement(
            "UPDATE zone_correction_configs
             SET resolved_config = resolved_config - 'pump_calibration'
             WHERE jsonb_exists(resolved_config, 'pump_calibration')"
        );

        DB::statement(
            "UPDATE zone_correction_config_versions
             SET resolved_config = resolved_config - 'pump_calibration'
             WHERE jsonb_exists(resolved_config, 'pump_calibration')"
        );
    }
};
