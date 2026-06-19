<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('zone_manual_schedules', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->string('task_type', 64);
            $table->string('schedule_kind', 16);
            $table->time('time_at')->nullable();
            $table->unsignedInteger('interval_sec')->nullable();
            $table->time('window_start')->nullable();
            $table->time('window_end')->nullable();
            $table->jsonb('days_of_week')->nullable();
            $table->timestampTz('run_at')->nullable();
            $table->timestampTz('last_dispatched_at')->nullable();
            $table->jsonb('payload')->default('{}');
            $table->string('label', 255)->nullable();
            $table->boolean('enabled')->default(true);
            $table->foreignId('created_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamps();

            $table->index(['zone_id', 'enabled'], 'zone_manual_schedules_zone_enabled_idx');
            $table->index(['zone_id', 'task_type'], 'zone_manual_schedules_zone_task_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('zone_manual_schedules');
    }
};
