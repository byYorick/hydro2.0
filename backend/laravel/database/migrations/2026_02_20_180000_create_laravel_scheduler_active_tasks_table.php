<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('laravel_scheduler_active_tasks', function (Blueprint $table) {
            $table->id();
            $table->string('task_id', 128)->unique();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->string('task_type', 64);
            $table->string('schedule_key', 255);
            $table->string('correlation_id', 255);
            $table->string('status', 32);
            $table->timestampTz('accepted_at');
            $table->timestampTz('due_at')->nullable();
            $table->timestampTz('expires_at')->nullable();
            $table->timestampTz('last_polled_at')->nullable();
            $table->timestampTz('terminal_at')->nullable();
            $table->jsonb('details')->default(DB::raw("'{}'::jsonb"));
            $table->timestampsTz();

            $table->index(['zone_id', 'status', 'updated_at'], 'lsat_zone_status_updated_idx');
            $table->index(['schedule_key', 'updated_at'], 'lsat_sched_key_updated_idx');
            $table->index('expires_at', 'lsat_expires_at_idx');
            $table->index('terminal_at', 'lsat_terminal_at_idx');
            $table->index('correlation_id', 'lsat_corr_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('laravel_scheduler_active_tasks');
    }
};

