<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (!Schema::hasTable('pid_state')) {
            Schema::create('pid_state', function (Blueprint $table) {
                $table->unsignedBigInteger('zone_id');
                $table->string('pid_type', 10);
                $table->float('integral')->default(0.0);
                $table->float('prev_error')->nullable();
                $table->unsignedBigInteger('last_output_ms')->default(0);
                $table->jsonb('stats')->nullable();
                $table->string('current_zone', 20)->nullable();
                $table->timestamp('created_at')->useCurrent();
                $table->timestamp('updated_at')->useCurrent();

                $table->primary(['zone_id', 'pid_type']);
                $table->foreign('zone_id')->references('id')->on('zones')->cascadeOnDelete();
                $table->index('zone_id', 'idx_pid_state_zone_id');
                $table->index('updated_at', 'idx_pid_state_updated_at');
            });
        }

        if (!Schema::hasTable('command_tracking')) {
            Schema::create('command_tracking', function (Blueprint $table) {
                $table->bigIncrements('id');
                $table->string('cmd_id', 100)->unique();
                $table->unsignedBigInteger('zone_id');
                $table->jsonb('command');
                $table->string('status', 20)->default('pending');
                $table->timestamp('sent_at')->useCurrent();
                $table->timestamp('completed_at')->nullable();
                $table->jsonb('response')->nullable();
                $table->text('error')->nullable();
                $table->float('latency_seconds')->nullable();
                $table->jsonb('context')->nullable();

                $table->foreign('zone_id')->references('id')->on('zones')->cascadeOnDelete();
                $table->index('zone_id', 'idx_command_tracking_zone_id');
                $table->index('status', 'idx_command_tracking_status');
                $table->index('sent_at', 'idx_command_tracking_sent_at');
                $table->index('cmd_id', 'idx_command_tracking_cmd_id');
            });
        }

        if (!Schema::hasTable('command_audit')) {
            Schema::create('command_audit', function (Blueprint $table) {
                $table->bigIncrements('id');
                $table->unsignedBigInteger('zone_id');
                $table->string('command_type', 50);
                $table->jsonb('command_data');
                $table->jsonb('telemetry_snapshot')->nullable();
                $table->jsonb('decision_context')->nullable();
                $table->jsonb('pid_state')->nullable();
                $table->timestamp('created_at')->useCurrent();

                $table->foreign('zone_id')->references('id')->on('zones')->cascadeOnDelete();
                $table->index('zone_id', 'idx_command_audit_zone_id');
                $table->index('created_at', 'idx_command_audit_created_at');
                $table->index('command_type', 'idx_command_audit_command_type');
            });
        }

        if (!Schema::hasTable('zone_automation_state')) {
            Schema::create('zone_automation_state', function (Blueprint $table) {
                $table->unsignedBigInteger('zone_id');
                $table->jsonb('state')->nullable();
                $table->timestamp('created_at')->useCurrent();
                $table->timestamp('updated_at')->useCurrent();

                $table->primary('zone_id');
                $table->foreign('zone_id')->references('id')->on('zones')->cascadeOnDelete();
            });
        }
    }

    public function down(): void
    {
        Schema::dropIfExists('zone_automation_state');
        Schema::dropIfExists('command_audit');
        Schema::dropIfExists('command_tracking');
        Schema::dropIfExists('pid_state');
    }
};
