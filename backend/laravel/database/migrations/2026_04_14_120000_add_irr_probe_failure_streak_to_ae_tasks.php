<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table): void {
            if (! Schema::hasColumn('ae_tasks', 'irr_probe_failure_streak')) {
                $table->smallInteger('irr_probe_failure_streak')
                    ->default(0)
                    ->after('stage_retry_count');
            }
        });

        DB::statement("
            DO \$\$
            BEGIN
                ALTER TABLE ae_tasks
                ADD CONSTRAINT ae_tasks_irr_probe_failure_streak_check
                CHECK (irr_probe_failure_streak >= 0);
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END
            \$\$;
        ");
    }

    public function down(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_irr_probe_failure_streak_check');

        Schema::table('ae_tasks', function (Blueprint $table): void {
            if (Schema::hasColumn('ae_tasks', 'irr_probe_failure_streak')) {
                $table->dropColumn('irr_probe_failure_streak');
            }
        });
    }
};
