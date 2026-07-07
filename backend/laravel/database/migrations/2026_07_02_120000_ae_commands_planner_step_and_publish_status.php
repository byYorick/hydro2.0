<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('ae_commands')) {
            return;
        }

        if (! Schema::hasColumn('ae_commands', 'planner_step')) {
            Schema::table('ae_commands', function (Blueprint $table) {
                $table->string('planner_step', 160)->nullable()->after('step_no');
            });
        }

        if ($this->isPgsql()) {
            DB::statement('ALTER TABLE ae_commands DROP CONSTRAINT IF EXISTS ae_commands_publish_status_check');
            DB::statement("
                ALTER TABLE ae_commands
                ADD CONSTRAINT ae_commands_publish_status_check
                CHECK (publish_status IN ('pending', 'published_unconfirmed', 'accepted', 'failed'))
            ");

            DB::statement('
                CREATE UNIQUE INDEX IF NOT EXISTS ae_commands_task_planner_step_unpublished_idx
                ON ae_commands (task_id, planner_step)
                WHERE planner_step IS NOT NULL
                  AND publish_status IN (\'pending\', \'published_unconfirmed\')
            ');
        }
    }

    public function down(): void
    {
        if (! Schema::hasTable('ae_commands')) {
            return;
        }

        if ($this->isPgsql()) {
            DB::statement('DROP INDEX IF EXISTS ae_commands_task_planner_step_unpublished_idx');

            DB::statement('ALTER TABLE ae_commands DROP CONSTRAINT IF EXISTS ae_commands_publish_status_check');
            DB::statement("
                ALTER TABLE ae_commands
                ADD CONSTRAINT ae_commands_publish_status_check
                CHECK (publish_status IN ('pending', 'accepted', 'failed'))
            ");
        }

        if (Schema::hasColumn('ae_commands', 'planner_step')) {
            Schema::table('ae_commands', function (Blueprint $table) {
                $table->dropColumn('planner_step');
            });
        }
    }

    private function isPgsql(): bool
    {
        return Schema::getConnection()->getDriverName() === 'pgsql';
    }
};
