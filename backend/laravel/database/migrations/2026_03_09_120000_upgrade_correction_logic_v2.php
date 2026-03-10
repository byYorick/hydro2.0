<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('ae_tasks', function (Blueprint $table) {
            if (! Schema::hasColumn('ae_tasks', 'corr_ec_attempt')) {
                $table->smallInteger('corr_ec_attempt')->nullable()->after('corr_attempt');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_ph_attempt')) {
                $table->smallInteger('corr_ph_attempt')->nullable()->after('corr_ec_attempt');
            }
        });

        DB::statement("
            UPDATE ae_tasks
            SET corr_ec_attempt = COALESCE(corr_ec_attempt, corr_attempt),
                corr_ph_attempt = COALESCE(corr_ph_attempt, corr_attempt)
            WHERE corr_step IS NOT NULL
        ");

        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_corr_step_check');
        DB::statement("
            ALTER TABLE ae_tasks
            ADD CONSTRAINT ae_tasks_corr_step_check
            CHECK (
                corr_step IS NULL
                OR corr_step IN (
                    'corr_activate',
                    'corr_wait_stable',
                    'corr_check',
                    'corr_dose_ec',
                    'corr_wait_ec',
                    'corr_dose_ph',
                    'corr_wait_ph',
                    'corr_dose_ph_piggyback',
                    'corr_wait_ph_piggyback',
                    'corr_deactivate',
                    'corr_done'
                )
            )
        ");
    }

    public function down(): void
    {
        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_corr_step_check');
        DB::statement("
            ALTER TABLE ae_tasks
            ADD CONSTRAINT ae_tasks_corr_step_check
            CHECK (
                corr_step IS NULL
                OR corr_step IN (
                    'corr_activate',
                    'corr_wait_stable',
                    'corr_check',
                    'corr_dose_ec',
                    'corr_wait_ec',
                    'corr_dose_ph',
                    'corr_wait_ph',
                    'corr_deactivate',
                    'corr_done'
                )
            )
        ");

        Schema::table('ae_tasks', function (Blueprint $table) {
            if (Schema::hasColumn('ae_tasks', 'corr_ph_attempt')) {
                $table->dropColumn('corr_ph_attempt');
            }
            if (Schema::hasColumn('ae_tasks', 'corr_ec_attempt')) {
                $table->dropColumn('corr_ec_attempt');
            }
        });
    }
};
