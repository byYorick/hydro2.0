<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (Schema::hasTable('ae_tasks')) {
            Schema::table('ae_tasks', function (Blueprint $table) {
                if (! Schema::hasColumn('ae_tasks', 'irrigation_mode')) {
                    $table->string('irrigation_mode', 16)->nullable()->after('intent_meta');
                }
                if (! Schema::hasColumn('ae_tasks', 'irrigation_requested_duration_sec')) {
                    $table->integer('irrigation_requested_duration_sec')->nullable()->after('irrigation_mode');
                }
                if (! Schema::hasColumn('ae_tasks', 'irrigation_decision_strategy')) {
                    $table->string('irrigation_decision_strategy', 64)->nullable()->after('irrigation_requested_duration_sec');
                }
                if (! Schema::hasColumn('ae_tasks', 'irrigation_decision_outcome')) {
                    $table->string('irrigation_decision_outcome', 32)->nullable()->after('irrigation_decision_strategy');
                }
                if (! Schema::hasColumn('ae_tasks', 'irrigation_decision_reason_code')) {
                    $table->string('irrigation_decision_reason_code', 128)->nullable()->after('irrigation_decision_outcome');
                }
                if (! Schema::hasColumn('ae_tasks', 'irrigation_decision_degraded')) {
                    $table->boolean('irrigation_decision_degraded')->nullable()->after('irrigation_decision_reason_code');
                }
                if (! Schema::hasColumn('ae_tasks', 'irrigation_replay_count')) {
                    $table->smallInteger('irrigation_replay_count')->default(0)->after('irrigation_decision_degraded');
                }
                if (! Schema::hasColumn('ae_tasks', 'irrigation_wait_ready_deadline_at')) {
                    $table->timestampTz('irrigation_wait_ready_deadline_at')->nullable()->after('irrigation_replay_count');
                }
                if (! Schema::hasColumn('ae_tasks', 'irrigation_setup_deadline_at')) {
                    $table->timestampTz('irrigation_setup_deadline_at')->nullable()->after('irrigation_wait_ready_deadline_at');
                }
            });
        }

        if (! $this->isPgsql()) {
            return;
        }

        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_task_type_check');
        DB::statement("
            ALTER TABLE ae_tasks
            ADD CONSTRAINT ae_tasks_task_type_check
            CHECK (task_type IN ('cycle_start', 'irrigation_start'))
        ");

        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_workflow_phase_check');
        DB::statement("
            ALTER TABLE ae_tasks
            ADD CONSTRAINT ae_tasks_workflow_phase_check
            CHECK (workflow_phase IN (
                'idle',
                'tank_filling',
                'tank_recirc',
                'ready',
                'irrigating',
                'irrig_recirc',
                'error'
            ))
        ");

        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_irrigation_mode_check');
        DB::statement("
            ALTER TABLE ae_tasks
            ADD CONSTRAINT ae_tasks_irrigation_mode_check
            CHECK (irrigation_mode IS NULL OR irrigation_mode IN ('normal', 'force'))
        ");

        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_irrigation_decision_outcome_check');
        DB::statement("
            ALTER TABLE ae_tasks
            ADD CONSTRAINT ae_tasks_irrigation_decision_outcome_check
            CHECK (
                irrigation_decision_outcome IS NULL
                OR irrigation_decision_outcome IN ('run', 'skip', 'degraded_run', 'fail')
            )
        ");

        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_irrigation_replay_count_check');
        DB::statement("
            ALTER TABLE ae_tasks
            ADD CONSTRAINT ae_tasks_irrigation_replay_count_check
            CHECK (irrigation_replay_count >= 0)
        ");
    }

    public function down(): void
    {
        if ($this->isPgsql()) {
            DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_irrigation_replay_count_check');
            DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_irrigation_decision_outcome_check');
            DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_irrigation_mode_check');

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

            DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_task_type_check');
            DB::statement("
                ALTER TABLE ae_tasks
                ADD CONSTRAINT ae_tasks_task_type_check
                CHECK (task_type = 'cycle_start')
            ");
        }

        if (Schema::hasTable('ae_tasks')) {
            Schema::table('ae_tasks', function (Blueprint $table) {
                $columns = [
                    'irrigation_mode',
                    'irrigation_requested_duration_sec',
                    'irrigation_decision_strategy',
                    'irrigation_decision_outcome',
                    'irrigation_decision_reason_code',
                    'irrigation_decision_degraded',
                    'irrigation_replay_count',
                    'irrigation_wait_ready_deadline_at',
                    'irrigation_setup_deadline_at',
                ];

                foreach ($columns as $column) {
                    if (Schema::hasColumn('ae_tasks', $column)) {
                        $table->dropColumn($column);
                    }
                }
            });
        }
    }

    private function isPgsql(): bool
    {
        return DB::getDriverName() === 'pgsql';
    }
};
