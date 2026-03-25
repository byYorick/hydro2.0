<?php

use App\Services\SystemAutomationSettingsCatalog;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('system_automation_settings')) {
            return;
        }

        $now = now();

        DB::table('system_automation_settings')->updateOrInsert(
            ['namespace' => 'process_calibration_defaults'],
            [
                'config' => json_encode(SystemAutomationSettingsCatalog::defaults('process_calibration_defaults'), JSON_THROW_ON_ERROR),
                'updated_by' => null,
                'created_at' => $now,
                'updated_at' => $now,
            ],
        );
    }

    public function down(): void
    {
        // Legacy system_automation_settings is removed by authority cleanup.
        // Rolling this data-only migration back is intentionally a no-op.
    }
};
