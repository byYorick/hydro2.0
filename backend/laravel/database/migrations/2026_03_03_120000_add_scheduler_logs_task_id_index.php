<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        DB::statement(
            "CREATE INDEX IF NOT EXISTS scheduler_logs_details_task_id_idx
             ON scheduler_logs ((details->>'task_id'))
             WHERE details->>'task_id' IS NOT NULL"
        );
    }

    public function down(): void
    {
        DB::statement('DROP INDEX IF EXISTS scheduler_logs_details_task_id_idx');
    }
};
