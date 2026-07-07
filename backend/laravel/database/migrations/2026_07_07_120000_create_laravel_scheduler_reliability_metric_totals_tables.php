<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('laravel_scheduler_missed_windows_totals', function (Blueprint $table): void {
            $table->id();
            $table->unsignedBigInteger('zone_id');
            $table->string('task_type', 64);
            $table->unsignedBigInteger('total')->default(0);
            $table->timestamps();

            $table->unique(['zone_id', 'task_type'], 'ls_missed_windows_unique');
        });

        Schema::create('laravel_scheduler_lock_skipped_totals', function (Blueprint $table): void {
            $table->id();
            $table->unsignedBigInteger('total')->default(0);
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('laravel_scheduler_lock_skipped_totals');
        Schema::dropIfExists('laravel_scheduler_missed_windows_totals');
    }
};
