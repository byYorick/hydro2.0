<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('laravel_scheduler_dispatch_metric_totals', function (Blueprint $table): void {
            $table->id();
            $table->unsignedBigInteger('zone_id');
            $table->string('task_type', 64);
            $table->string('result', 64);
            $table->unsignedBigInteger('total')->default(0);
            $table->timestamps();

            $table->unique(['zone_id', 'task_type', 'result'], 'ls_dispatch_metric_unique');
            $table->index(['task_type', 'result'], 'ls_dispatch_metric_task_result_idx');
        });

        Schema::create('laravel_scheduler_cycle_duration_aggregates', function (Blueprint $table): void {
            $table->id();
            $table->string('dispatch_mode', 64);
            $table->unsignedBigInteger('sample_count')->default(0);
            $table->double('sample_sum')->default(0);
            $table->timestamps();

            $table->unique('dispatch_mode', 'ls_cycle_duration_agg_mode_unique');
        });

        Schema::create('laravel_scheduler_cycle_duration_bucket_counts', function (Blueprint $table): void {
            $table->id();
            $table->string('dispatch_mode', 64);
            $table->string('bucket_le', 32);
            $table->unsignedBigInteger('sample_count')->default(0);
            $table->timestamps();

            $table->unique(['dispatch_mode', 'bucket_le'], 'ls_cycle_duration_bucket_unique');
            $table->index('dispatch_mode', 'ls_cycle_duration_bucket_mode_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('laravel_scheduler_cycle_duration_bucket_counts');
        Schema::dropIfExists('laravel_scheduler_cycle_duration_aggregates');
        Schema::dropIfExists('laravel_scheduler_dispatch_metric_totals');
    }
};
