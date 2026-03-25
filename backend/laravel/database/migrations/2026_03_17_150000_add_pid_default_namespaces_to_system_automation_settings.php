<?php

use Illuminate\Database\Migrations\Migration;

return new class extends Migration
{
    public function up(): void
    {
        // system.pid_defaults.* removed from the canonical authority model.
        // Legacy backfill of pid_defaults into system_automation_settings is intentionally skipped.
    }

    public function down(): void
    {
        // Legacy system_automation_settings is removed by authority cleanup.
        // Rolling this data-only migration back is intentionally a no-op.
    }
};
