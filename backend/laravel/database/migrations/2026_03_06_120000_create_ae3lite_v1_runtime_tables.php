<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        $this->extendZonesTable();
        $this->extendZoneWorkflowStateTable();
        $this->createAeTasksTable();
        $this->createAeCommandsTable();
        $this->createAeZoneLeasesTable();
        $this->addPgsqlConstraintsAndIndexes();
    }

    public function down(): void
    {
        $this->dropPgsqlConstraintsAndIndexes();

        Schema::dropIfExists('ae_zone_leases');
        Schema::dropIfExists('ae_commands');
        Schema::dropIfExists('ae_tasks');

        if (Schema::hasTable('zones') && Schema::hasColumn('zones', 'automation_runtime')) {
            DB::statement('DROP INDEX IF EXISTS zones_automation_runtime_idx');

            Schema::table('zones', function (Blueprint $table) {
                $table->dropColumn('automation_runtime');
            });
        }

        if (Schema::hasTable('zone_workflow_state') && Schema::hasColumn('zone_workflow_state', 'version')) {
            Schema::table('zone_workflow_state', function (Blueprint $table) {
                $table->dropColumn('version');
            });
        }
    }

    private function extendZonesTable(): void
    {
        if (! Schema::hasTable('zones') || Schema::hasColumn('zones', 'automation_runtime')) {
            return;
        }

        Schema::table('zones', function (Blueprint $table) {
            $table->string('automation_runtime', 16)->default('ae2');
            $table->index('automation_runtime', 'zones_automation_runtime_idx');
        });
    }

    private function extendZoneWorkflowStateTable(): void
    {
        if (! Schema::hasTable('zone_workflow_state') || Schema::hasColumn('zone_workflow_state', 'version')) {
            return;
        }

        Schema::table('zone_workflow_state', function (Blueprint $table) {
            $table->unsignedBigInteger('version')->default(0);
        });
    }

    private function createAeTasksTable(): void
    {
        if (Schema::hasTable('ae_tasks')) {
            return;
        }

        Schema::create('ae_tasks', function (Blueprint $table) {
            $table->bigIncrements('id');
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->string('task_type', 64);
            $table->string('status', 32);
            $table->jsonb('payload')->default(DB::raw("'{}'::jsonb"));
            $table->string('idempotency_key', 191);
            $table->timestampTz('scheduled_for');
            $table->timestampTz('due_at');
            $table->string('claimed_by', 191)->nullable();
            $table->timestampTz('claimed_at')->nullable();
            $table->string('error_code', 128)->nullable();
            $table->text('error_message')->nullable();
            $table->timestampTz('created_at')->useCurrent();
            $table->timestampTz('updated_at')->useCurrent();
            $table->timestampTz('completed_at')->nullable();

            $table->unique('idempotency_key', 'ae_tasks_idempotency_key_unique');
            $table->index(['zone_id', 'status'], 'ae_tasks_zone_status_idx');
        });
    }

    private function createAeCommandsTable(): void
    {
        if (Schema::hasTable('ae_commands')) {
            return;
        }

        Schema::create('ae_commands', function (Blueprint $table) {
            $table->bigIncrements('id');
            $table->foreignId('task_id')->constrained('ae_tasks')->cascadeOnDelete();
            $table->unsignedInteger('step_no');
            $table->string('node_uid', 128);
            $table->string('channel', 64);
            $table->jsonb('payload')->default(DB::raw("'{}'::jsonb"));
            $table->string('external_id', 191)->nullable();
            $table->string('publish_status', 32)->default('pending');
            $table->string('terminal_status', 32)->nullable();
            $table->timestampTz('ack_received_at')->nullable();
            $table->timestampTz('terminal_at')->nullable();
            $table->text('last_error')->nullable();
            $table->timestampTz('created_at')->useCurrent();
            $table->timestampTz('updated_at')->useCurrent();

            $table->unique(['task_id', 'step_no'], 'ae_commands_task_step_unique');
        });
    }

    private function createAeZoneLeasesTable(): void
    {
        if (Schema::hasTable('ae_zone_leases')) {
            return;
        }

        Schema::create('ae_zone_leases', function (Blueprint $table) {
            $table->foreignId('zone_id')->primary()->constrained('zones')->cascadeOnDelete();
            $table->string('owner', 191);
            $table->timestampTz('leased_until');
            $table->timestampTz('updated_at')->useCurrent();
        });
    }

    private function addPgsqlConstraintsAndIndexes(): void
    {
        if (! $this->isPgsql()) {
            return;
        }

        DB::statement("
            DO $$
            BEGIN
                ALTER TABLE zones
                ADD CONSTRAINT zones_automation_runtime_check
                CHECK (automation_runtime IN ('ae2', 'ae3'));
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        ");

        DB::statement("
            DO $$
            BEGIN
                ALTER TABLE ae_tasks
                ADD CONSTRAINT ae_tasks_task_type_check
                CHECK (task_type = 'cycle_start');
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        ");

        DB::statement("
            DO $$
            BEGIN
                ALTER TABLE ae_tasks
                ADD CONSTRAINT ae_tasks_status_check
                CHECK (status IN ('pending', 'claimed', 'running', 'waiting_command', 'completed', 'failed', 'cancelled'));
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        ");

        DB::statement("
            DO $$
            BEGIN
                ALTER TABLE ae_commands
                ADD CONSTRAINT ae_commands_step_no_check
                CHECK (step_no >= 1);
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        ");

        DB::statement("
            DO $$
            BEGIN
                ALTER TABLE ae_commands
                ADD CONSTRAINT ae_commands_publish_status_check
                CHECK (publish_status IN ('pending', 'accepted', 'failed'));
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        ");

        DB::statement("
            DO $$
            BEGIN
                ALTER TABLE ae_commands
                ADD CONSTRAINT ae_commands_terminal_status_check
                CHECK (
                    terminal_status IS NULL
                    OR terminal_status IN ('DONE', 'NO_EFFECT', 'ERROR', 'INVALID', 'BUSY', 'TIMEOUT', 'SEND_FAILED')
                );
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        ");

        DB::statement("
            CREATE UNIQUE INDEX IF NOT EXISTS ae_tasks_active_zone_unique
            ON ae_tasks (zone_id)
            WHERE status IN ('pending', 'claimed', 'running', 'waiting_command')
        ");

        DB::statement("
            CREATE INDEX IF NOT EXISTS ae_tasks_pending_idx
            ON ae_tasks (due_at, created_at)
            WHERE status = 'pending'
        ");

        DB::statement("
            CREATE INDEX IF NOT EXISTS ae_commands_external_id_idx
            ON ae_commands (external_id)
            WHERE external_id IS NOT NULL
        ");
    }

    private function dropPgsqlConstraintsAndIndexes(): void
    {
        if (! $this->isPgsql()) {
            return;
        }

        DB::statement('DROP INDEX IF EXISTS ae_commands_external_id_idx');
        DB::statement('DROP INDEX IF EXISTS ae_tasks_pending_idx');
        DB::statement('DROP INDEX IF EXISTS ae_tasks_active_zone_unique');

        DB::statement('ALTER TABLE ae_commands DROP CONSTRAINT IF EXISTS ae_commands_terminal_status_check');
        DB::statement('ALTER TABLE ae_commands DROP CONSTRAINT IF EXISTS ae_commands_publish_status_check');
        DB::statement('ALTER TABLE ae_commands DROP CONSTRAINT IF EXISTS ae_commands_step_no_check');
        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_status_check');
        DB::statement('ALTER TABLE ae_tasks DROP CONSTRAINT IF EXISTS ae_tasks_task_type_check');
        DB::statement('ALTER TABLE zones DROP CONSTRAINT IF EXISTS zones_automation_runtime_check');
    }

    private function isPgsql(): bool
    {
        return DB::getDriverName() === 'pgsql';
    }
};
