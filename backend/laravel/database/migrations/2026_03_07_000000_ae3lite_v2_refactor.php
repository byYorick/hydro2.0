<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * AE3-Lite v2: замена payload JSONB на явные типизированные колонки.
 *
 * - ae_tasks: добавляем intent, workflow state, correction state колонки; удаляем payload
 * - ae_commands: добавляем stage_name
 * - ae_stage_transitions: новая audit-trail таблица (INSERT-only)
 */
return new class extends Migration
{
    public function up(): void
    {
        $this->addIntentColumnsToAeTasks();
        $this->addWorkflowStateColumnsToAeTasks();
        $this->addCorrectionStateColumnsToAeTasks();
        $this->dropPayloadFromAeTasks();
        $this->addStageNameToAeCommands();
        $this->createAeStageTransitionsTable();
        $this->addPgsqlConstraintsAndIndexes();
    }

    public function down(): void
    {
        $this->dropPgsqlConstraintsAndIndexes();

        Schema::dropIfExists('ae_stage_transitions');

        if (Schema::hasTable('ae_commands') && Schema::hasColumn('ae_commands', 'stage_name')) {
            Schema::table('ae_commands', function (Blueprint $table) {
                $table->dropColumn('stage_name');
            });
        }

        // Восстанавливаем payload
        if (Schema::hasTable('ae_tasks') && ! Schema::hasColumn('ae_tasks', 'payload')) {
            Schema::table('ae_tasks', function (Blueprint $table) {
                $table->jsonb('payload')->default(DB::raw("'{}'::jsonb"));
            });
        }

        // Удаляем correction state колонки
        $corrColumns = [
            'corr_step', 'corr_attempt', 'corr_max_attempts', 'corr_activated_here',
            'corr_stabilization_sec', 'corr_return_stage_success', 'corr_return_stage_fail',
            'corr_outcome_success', 'corr_needs_ec', 'corr_ec_node_uid', 'corr_ec_channel',
            'corr_ec_duration_ms', 'corr_needs_ph_up', 'corr_needs_ph_down', 'corr_ph_node_uid',
            'corr_ph_channel', 'corr_ph_duration_ms', 'corr_wait_until',
        ];
        $this->dropColumnsIfExist('ae_tasks', $corrColumns);

        // Удаляем workflow state колонки
        $workflowColumns = [
            'topology', 'current_stage', 'workflow_phase',
            'stage_deadline_at', 'stage_retry_count', 'stage_entered_at', 'clean_fill_cycle',
        ];
        $this->dropColumnsIfExist('ae_tasks', $workflowColumns);

        // Удаляем intent колонки
        $intentColumns = ['intent_source', 'intent_trigger', 'intent_id', 'intent_meta'];
        $this->dropColumnsIfExist('ae_tasks', $intentColumns);
    }

    // ─── ae_tasks: intent metadata (write-once) ────────────────────────

    private function addIntentColumnsToAeTasks(): void
    {
        if (! Schema::hasTable('ae_tasks') || Schema::hasColumn('ae_tasks', 'intent_source')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table) {
            $table->string('intent_source', 64)->nullable()->after('payload');
            $table->string('intent_trigger', 64)->nullable()->after('intent_source');
            $table->unsignedBigInteger('intent_id')->nullable()->after('intent_trigger');
            $table->jsonb('intent_meta')->default(DB::raw("'{}'::jsonb"))->after('intent_id');
        });
    }

    // ─── ae_tasks: workflow state machine (mutable) ────────────────────

    private function addWorkflowStateColumnsToAeTasks(): void
    {
        if (! Schema::hasTable('ae_tasks') || Schema::hasColumn('ae_tasks', 'topology')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table) {
            $table->string('topology', 64)->default('two_tank')->after('intent_meta');
            $table->string('current_stage', 64)->default('startup')->after('topology');
            $table->string('workflow_phase', 32)->default('idle')->after('current_stage');
            $table->timestampTz('stage_deadline_at')->nullable()->after('workflow_phase');
            $table->smallInteger('stage_retry_count')->default(0)->after('stage_deadline_at');
            $table->timestampTz('stage_entered_at')->nullable()->after('stage_retry_count');
            $table->smallInteger('clean_fill_cycle')->default(0)->after('stage_entered_at');
        });
    }

    // ─── ae_tasks: correction state (all nullable — NULL when inactive) ─

    private function addCorrectionStateColumnsToAeTasks(): void
    {
        if (! Schema::hasTable('ae_tasks') || Schema::hasColumn('ae_tasks', 'corr_step')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table) {
            $table->string('corr_step', 32)->nullable()->after('clean_fill_cycle');
            $table->smallInteger('corr_attempt')->nullable()->after('corr_step');
            $table->smallInteger('corr_max_attempts')->nullable()->after('corr_attempt');
            $table->boolean('corr_activated_here')->nullable()->after('corr_max_attempts');
            $table->smallInteger('corr_stabilization_sec')->nullable()->after('corr_activated_here');
            $table->string('corr_return_stage_success', 64)->nullable()->after('corr_stabilization_sec');
            $table->string('corr_return_stage_fail', 64)->nullable()->after('corr_return_stage_success');
            $table->boolean('corr_outcome_success')->nullable()->after('corr_return_stage_fail');
            $table->boolean('corr_needs_ec')->nullable()->after('corr_outcome_success');
            $table->string('corr_ec_node_uid', 128)->nullable()->after('corr_needs_ec');
            $table->string('corr_ec_channel', 64)->nullable()->after('corr_ec_node_uid');
            $table->integer('corr_ec_duration_ms')->nullable()->after('corr_ec_channel');
            $table->boolean('corr_needs_ph_up')->nullable()->after('corr_ec_duration_ms');
            $table->boolean('corr_needs_ph_down')->nullable()->after('corr_needs_ph_up');
            $table->string('corr_ph_node_uid', 128)->nullable()->after('corr_needs_ph_down');
            $table->string('corr_ph_channel', 64)->nullable()->after('corr_ph_node_uid');
            $table->integer('corr_ph_duration_ms')->nullable()->after('corr_ph_channel');
            $table->timestampTz('corr_wait_until')->nullable()->after('corr_ph_duration_ms');
        });
    }

    // ─── ae_tasks: удаляем старый payload ──────────────────────────────

    private function dropPayloadFromAeTasks(): void
    {
        if (! Schema::hasTable('ae_tasks') || ! Schema::hasColumn('ae_tasks', 'payload')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table) {
            $table->dropColumn('payload');
        });
    }

    // ─── ae_commands: stage_name для привязки к stage ──────────────────

    private function addStageNameToAeCommands(): void
    {
        if (! Schema::hasTable('ae_commands') || Schema::hasColumn('ae_commands', 'stage_name')) {
            return;
        }

        Schema::table('ae_commands', function (Blueprint $table) {
            $table->string('stage_name', 64)->nullable()->after('task_id');
        });
    }

    // ─── ae_stage_transitions: audit trail (INSERT-only) ───────────────

    private function createAeStageTransitionsTable(): void
    {
        if (Schema::hasTable('ae_stage_transitions')) {
            return;
        }

        Schema::create('ae_stage_transitions', function (Blueprint $table) {
            $table->bigIncrements('id');
            $table->foreignId('task_id')->constrained('ae_tasks')->cascadeOnDelete();
            $table->string('from_stage', 64)->nullable();
            $table->string('to_stage', 64);
            $table->string('workflow_phase', 32)->nullable();
            $table->timestampTz('triggered_at');
            $table->jsonb('metadata')->default(DB::raw("'{}'::jsonb"));
            $table->timestampTz('created_at')->useCurrent();
        });
    }

    // ─── PostgreSQL constraints & indexes ──────────────────────────────

    private function addPgsqlConstraintsAndIndexes(): void
    {
        if (! $this->isPgsql()) {
            return;
        }

        // ae_tasks: topology не пустая
        DB::statement("
            DO $$
            BEGIN
                ALTER TABLE ae_tasks
                ADD CONSTRAINT ae_tasks_topology_check
                CHECK (topology <> '');
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        ");

        // ae_tasks: current_stage не пустая
        DB::statement("
            DO $$
            BEGIN
                ALTER TABLE ae_tasks
                ADD CONSTRAINT ae_tasks_current_stage_check
                CHECK (current_stage <> '');
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        ");

        // ae_tasks: workflow_phase enum
        DB::statement("
            DO $$
            BEGIN
                ALTER TABLE ae_tasks
                ADD CONSTRAINT ae_tasks_workflow_phase_check
                CHECK (workflow_phase IN ('idle', 'filling', 'correcting', 'recirculation', 'ready', 'error'));
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        ");

        // ae_tasks: stage_retry_count >= 0
        DB::statement("
            DO $$
            BEGIN
                ALTER TABLE ae_tasks
                ADD CONSTRAINT ae_tasks_stage_retry_count_check
                CHECK (stage_retry_count >= 0);
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        ");

        // ae_tasks: clean_fill_cycle >= 0
        DB::statement("
            DO $$
            BEGIN
                ALTER TABLE ae_tasks
                ADD CONSTRAINT ae_tasks_clean_fill_cycle_check
                CHECK (clean_fill_cycle >= 0);
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        ");

        // ae_tasks: corr_step enum (или NULL)
        DB::statement("
            DO $$
            BEGIN
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
                );
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        ");

        // Index: ae_tasks по (topology, current_stage) для active tasks
        DB::statement("
            CREATE INDEX IF NOT EXISTS ae_tasks_topology_stage_idx
            ON ae_tasks (topology, current_stage)
            WHERE status IN ('running', 'waiting_command')
        ");

        // Index: ae_tasks по stage_deadline_at для timeout polling
        DB::statement("
            CREATE INDEX IF NOT EXISTS ae_tasks_deadline_idx
            ON ae_tasks (stage_deadline_at)
            WHERE stage_deadline_at IS NOT NULL
              AND status IN ('running', 'waiting_command')
        ");

        // Index: ae_commands по (task_id, stage_name)
        DB::statement("
            CREATE INDEX IF NOT EXISTS ae_commands_stage_idx
            ON ae_commands (task_id, stage_name)
            WHERE stage_name IS NOT NULL
        ");

        // Index: ae_stage_transitions по (task_id, triggered_at)
        DB::statement("
            CREATE INDEX IF NOT EXISTS ae_stage_transitions_task_idx
            ON ae_stage_transitions (task_id, triggered_at)
        ");
    }

    private function dropPgsqlConstraintsAndIndexes(): void
    {
        if (! $this->isPgsql()) {
            return;
        }

        DB::statement('DROP INDEX IF EXISTS ae_stage_transitions_task_idx');
        DB::statement('DROP INDEX IF EXISTS ae_commands_stage_idx');
        DB::statement('DROP INDEX IF EXISTS ae_tasks_deadline_idx');
        DB::statement('DROP INDEX IF EXISTS ae_tasks_topology_stage_idx');

        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_corr_step_check');
        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_clean_fill_cycle_check');
        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_stage_retry_count_check');
        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_workflow_phase_check');
        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_current_stage_check');
        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_topology_check');
    }

    // ─── Helpers ───────────────────────────────────────────────────────

    private function dropColumnsIfExist(string $table, array $columns): void
    {
        if (! Schema::hasTable($table)) {
            return;
        }

        $existing = array_filter($columns, fn (string $col) => Schema::hasColumn($table, $col));

        if ($existing) {
            Schema::table($table, function (Blueprint $table) use ($existing) {
                $table->dropColumn($existing);
            });
        }
    }

    private function isPgsql(): bool
    {
        return DB::getDriverName() === 'pgsql';
    }
};
