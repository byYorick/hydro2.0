<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * AE3-Lite v2: исправление CHECK constraints, несовместимых с кодом.
 *
 * Проблема 1: workflow_phase constraint использует ('filling', 'correcting', 'recirculation')
 *             вместо реальных значений кода ('tank_filling', 'tank_recirc').
 *
 * Проблема 2: corr_step constraint использует ('corr_activate_sensors', 'corr_wait_stabilize',
 *             'corr_deactivate_sensors', 'corr_verify') вместо реальных шагов кода
 *             ('corr_activate', 'corr_wait_stable', 'corr_wait_ec', 'corr_wait_ph', 'corr_deactivate').
 */
return new class extends Migration
{
    public function up(): void
    {
        if (! $this->isPgsql()) {
            return;
        }

        // Fix 1: workflow_phase — заменяем constraint на реальные значения из topology_registry
        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_workflow_phase_check');
        DB::statement("
            ALTER TABLE ae_tasks
            ADD CONSTRAINT ae_tasks_workflow_phase_check
            CHECK (workflow_phase IN (
                'idle',
                'tank_filling',
                'tank_recirc',
                'ready',
                'error'
            ))
        ");

        // Fix 2: corr_step — заменяем constraint на реальные шаги CorrectionHandler
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
    }

    public function down(): void
    {
        if (! $this->isPgsql()) {
            return;
        }

        // Откат к значениям из исходной миграции (v2_refactor)
        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_workflow_phase_check');
        DB::statement("
            ALTER TABLE ae_tasks
            ADD CONSTRAINT ae_tasks_workflow_phase_check
            CHECK (workflow_phase IN ('idle', 'filling', 'correcting', 'recirculation', 'ready', 'error'))
        ");

        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_corr_step_check');
        DB::statement("
            ALTER TABLE ae_tasks
            ADD CONSTRAINT ae_tasks_corr_step_check
            CHECK (
                corr_step IS NULL
                OR corr_step IN (
                    'corr_check', 'corr_activate_sensors',
                    'corr_dose_ec', 'corr_dose_ph',
                    'corr_wait_stabilize', 'corr_verify',
                    'corr_deactivate_sensors', 'corr_done'
                )
            )
        ");
    }

    private function isPgsql(): bool
    {
        return DB::getDriverName() === 'pgsql';
    }
};
