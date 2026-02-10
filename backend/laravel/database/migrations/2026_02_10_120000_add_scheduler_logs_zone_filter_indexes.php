<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        DB::statement(
            "CREATE INDEX IF NOT EXISTS scheduler_logs_task_zone_created_idx
             ON scheduler_logs (task_name, ((details->>'zone_id')), created_at DESC, id DESC)"
        );

        DB::statement(
            "CREATE INDEX IF NOT EXISTS scheduler_logs_zone_created_idx
             ON scheduler_logs (((details->>'zone_id')), created_at DESC, id DESC)
             WHERE task_name LIKE 'ae_scheduler_task_st-%'"
        );
    }

    public function down(): void
    {
        DB::statement('DROP INDEX IF EXISTS scheduler_logs_task_zone_created_idx');
        DB::statement('DROP INDEX IF EXISTS scheduler_logs_zone_created_idx');
    }
};

