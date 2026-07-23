<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Allow sequential-nutrient dilute FSM steps on ae_tasks.corr_step.
 *
 * Runtime uses corr_dilute_pulse / corr_dilute_settle (correction.py);
 * without these values ae_tasks_corr_step_check rejects enter_correction.
 */
return new class extends Migration
{
    public function up(): void
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
                    'corr_dose_ph_piggyback',
                    'corr_wait_ph_piggyback',
                    'corr_dilute_pulse',
                    'corr_dilute_settle',
                    'corr_deactivate',
                    'corr_done'
                )
            )
        ");
    }

    public function down(): void
    {
        DB::statement("
            UPDATE ae_tasks
            SET corr_step = 'corr_check'
            WHERE corr_step IN ('corr_dilute_pulse', 'corr_dilute_settle')
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
};
