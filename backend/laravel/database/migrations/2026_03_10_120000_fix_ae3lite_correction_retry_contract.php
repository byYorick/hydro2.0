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

        Schema::table('ae_tasks', function (Blueprint $table) {
            if (! Schema::hasColumn('ae_tasks', 'corr_ec_max_attempts')) {
                $table->smallInteger('corr_ec_max_attempts')->nullable()->after('corr_ec_attempt');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_ph_max_attempts')) {
                $table->smallInteger('corr_ph_max_attempts')->nullable()->after('corr_ph_attempt');
            }
        });

        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_corr_ec_max_attempts_check');
        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_corr_ph_max_attempts_check');
        DB::statement(<<<'SQL'
            ALTER TABLE ae_tasks
            ADD CONSTRAINT ae_tasks_corr_ec_max_attempts_check
            CHECK (corr_ec_max_attempts IS NULL OR corr_ec_max_attempts >= 1)
        SQL);
        DB::statement(<<<'SQL'
            ALTER TABLE ae_tasks
            ADD CONSTRAINT ae_tasks_corr_ph_max_attempts_check
            CHECK (corr_ph_max_attempts IS NULL OR corr_ph_max_attempts >= 1)
        SQL);
    }

    public function down(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_corr_ec_max_attempts_check');
        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_corr_ph_max_attempts_check');

        Schema::table('ae_tasks', function (Blueprint $table) {
            $columns = array_values(array_filter([
                Schema::hasColumn('ae_tasks', 'corr_ph_max_attempts') ? 'corr_ph_max_attempts' : null,
                Schema::hasColumn('ae_tasks', 'corr_ec_max_attempts') ? 'corr_ec_max_attempts' : null,
            ]));

            if ($columns !== []) {
                $table->dropColumn($columns);
            }
        });
    }
};
