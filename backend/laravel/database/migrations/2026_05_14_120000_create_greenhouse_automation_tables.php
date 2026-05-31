<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('greenhouse_automation_intents', function (Blueprint $table) {
            $table->id();
            $table->foreignId('greenhouse_id')->constrained('greenhouses')->restrictOnDelete();
            $table->string('intent_type', 64)->default('GREENHOUSE_CLIMATE_TICK');
            $table->string('task_type', 64)->default('greenhouse_climate_tick');
            $table->string('intent_source', 64)->nullable();
            $table->string('idempotency_key', 191);
            $table->string('status', 32)->default('pending');
            $table->timestampTz('not_before')->nullable();
            $table->timestampTz('claimed_at')->nullable();
            $table->timestampTz('completed_at')->nullable();
            $table->string('error_code', 128)->nullable();
            $table->text('error_message')->nullable();
            $table->unsignedInteger('retry_count')->default(0);
            $table->unsignedInteger('max_retries')->default(3);
            $table->timestampsTz();

            $table->unique(['greenhouse_id', 'idempotency_key'], 'gh_automation_intents_gh_idempotency_unique');
            $table->index(['greenhouse_id', 'status'], 'gh_automation_intents_gh_status_idx');
            $table->index(['status', 'not_before'], 'gh_automation_intents_status_not_before_idx');
        });

        if (DB::getDriverName() === 'pgsql') {
            DB::statement(
                "DO $$
                 BEGIN
                     ALTER TABLE greenhouse_automation_intents
                     ADD CONSTRAINT greenhouse_automation_intents_status_check
                     CHECK (status IN ('pending','claimed','running','completed','failed','cancelled'));
                 EXCEPTION
                     WHEN duplicate_object THEN NULL;
                 END $$;"
            );
            DB::statement(
                "CREATE UNIQUE INDEX IF NOT EXISTS greenhouse_automation_intents_one_active_idx
                 ON greenhouse_automation_intents (greenhouse_id)
                 WHERE status IN ('pending','claimed','running')"
            );
        }

        Schema::create('greenhouse_automation_tasks', function (Blueprint $table) {
            $table->id();
            $table->foreignId('greenhouse_id')->constrained('greenhouses')->restrictOnDelete();
            $table->foreignId('intent_id')->nullable()->constrained('greenhouse_automation_intents')->nullOnDelete();
            $table->string('task_type', 64)->default('greenhouse_climate_tick');
            $table->string('status', 32)->default('running');
            $table->string('idempotency_key', 191);
            $table->string('workflow_stage', 64)->nullable();
            $table->jsonb('decision_snapshot')->nullable();
            $table->jsonb('command_refs')->nullable();
            $table->string('error_code', 128)->nullable();
            $table->text('error_message')->nullable();
            $table->timestampTz('completed_at')->nullable();
            $table->timestampsTz();

            $table->unique(['greenhouse_id', 'idempotency_key'], 'gh_automation_tasks_gh_idempotency_unique');
            $table->index(['greenhouse_id', 'status'], 'gh_automation_tasks_gh_status_idx');
        });

        if (DB::getDriverName() === 'pgsql') {
            DB::statement(
                "DO $$
                 BEGIN
                     ALTER TABLE greenhouse_automation_tasks
                     ADD CONSTRAINT greenhouse_automation_tasks_status_check
                     CHECK (status IN ('claimed','running','waiting_command','completed','failed','cancelled'));
                 EXCEPTION
                     WHEN duplicate_object THEN NULL;
                 END $$;"
            );
            DB::statement(
                "DO $$
                 BEGIN
                     ALTER TABLE greenhouse_automation_tasks
                     ADD CONSTRAINT greenhouse_automation_tasks_task_type_check
                     CHECK (task_type = 'greenhouse_climate_tick');
                 EXCEPTION
                     WHEN duplicate_object THEN NULL;
                 END $$;"
            );
            DB::statement(
                "CREATE UNIQUE INDEX IF NOT EXISTS greenhouse_automation_tasks_one_active_idx
                 ON greenhouse_automation_tasks (greenhouse_id)
                 WHERE status IN ('claimed','running','waiting_command')"
            );
        }

        Schema::create('greenhouse_automation_leases', function (Blueprint $table) {
            $table->foreignId('greenhouse_id')->primary()->constrained('greenhouses')->restrictOnDelete();
            $table->string('owner', 64)->default('ae3_greenhouse_climate');
            $table->timestampTz('leased_until');
            $table->timestampTz('updated_at');
        });

        Schema::create('greenhouse_automation_state', function (Blueprint $table) {
            $table->foreignId('greenhouse_id')->primary()->constrained('greenhouses')->restrictOnDelete();
            $table->boolean('climate_enabled')->default(false);
            $table->string('control_mode', 16)->default('auto');
            $table->timestampTz('next_scheduled_tick_at')->nullable();
            $table->unsignedSmallInteger('left_position_pct')->default(0);
            $table->unsignedSmallInteger('right_position_pct')->default(0);
            $table->unsignedSmallInteger('recommended_left_position_pct')->default(0);
            $table->unsignedSmallInteger('recommended_right_position_pct')->default(0);
            $table->unsignedSmallInteger('last_sent_left_position_pct')->nullable();
            $table->unsignedSmallInteger('last_sent_right_position_pct')->nullable();
            $table->text('decision_reason')->nullable();
            $table->jsonb('decision_factors')->nullable();
            $table->boolean('weather_fresh')->default(false);
            $table->boolean('inside_climate_fresh')->default(false);
            $table->unsignedBigInteger('active_manual_override_id')->nullable()->index('gh_automation_state_active_override_idx');
            $table->foreignId('last_task_id')->nullable()->constrained('greenhouse_automation_tasks')->nullOnDelete();
            $table->string('last_error_code', 128)->nullable();
            $table->text('last_error_message')->nullable();
            $table->jsonb('active_alerts_summary')->nullable();
            $table->timestampTz('last_decision_at')->nullable();
            $table->timestampTz('last_command_at')->nullable();
            $table->string('last_left_cmd_id', 128)->nullable();
            $table->string('last_right_cmd_id', 128)->nullable();
            $table->timestampsTz();
        });

        Schema::create('greenhouse_manual_overrides', function (Blueprint $table) {
            $table->id();
            $table->foreignId('greenhouse_id')->constrained('greenhouses')->restrictOnDelete();
            $table->unsignedSmallInteger('left_position_pct');
            $table->unsignedSmallInteger('right_position_pct');
            $table->unsignedInteger('ttl_sec');
            $table->string('return_mode', 16)->default('auto');
            $table->string('reason', 500)->nullable();
            $table->timestampTz('expires_at');
            $table->foreignId('created_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestampsTz();

            $table->index(['greenhouse_id', 'expires_at'], 'gh_manual_overrides_gh_expires_idx');
        });
    }

    public function down(): void
    {
        if (DB::getDriverName() === 'pgsql') {
            try {
                DB::statement(
                    'ALTER TABLE greenhouse_automation_intents DROP CONSTRAINT IF EXISTS greenhouse_automation_intents_status_check'
                );
                DB::statement(
                    'ALTER TABLE greenhouse_automation_tasks DROP CONSTRAINT IF EXISTS greenhouse_automation_tasks_status_check'
                );
                DB::statement(
                    'ALTER TABLE greenhouse_automation_tasks DROP CONSTRAINT IF EXISTS greenhouse_automation_tasks_task_type_check'
                );
            } catch (\Throwable) {
            }
        }

        Schema::dropIfExists('greenhouse_automation_state');
        Schema::dropIfExists('greenhouse_automation_leases');
        Schema::dropIfExists('greenhouse_automation_tasks');
        Schema::dropIfExists('greenhouse_manual_overrides');
        Schema::dropIfExists('greenhouse_automation_intents');
    }
};
