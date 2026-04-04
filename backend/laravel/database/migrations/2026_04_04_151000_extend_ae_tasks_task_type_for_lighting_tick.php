<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_task_type_check');
        DB::statement("
            ALTER TABLE ae_tasks
            ADD CONSTRAINT ae_tasks_task_type_check
            CHECK (task_type IN ('cycle_start', 'irrigation_start', 'lighting_tick'))
        ");
    }

    public function down(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_task_type_check');
        DB::statement("
            ALTER TABLE ae_tasks
            ADD CONSTRAINT ae_tasks_task_type_check
            CHECK (task_type IN ('cycle_start', 'irrigation_start'))
        ");
    }
};
