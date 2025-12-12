<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('grow_cycles', function (Blueprint $table) {
            $table->id();
            $table->foreignId('greenhouse_id')->constrained('greenhouses')->cascadeOnDelete();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->foreignId('plant_id')->nullable()->constrained('plants')->nullOnDelete();
            $table->foreignId('recipe_id')->nullable()->constrained('recipes')->nullOnDelete();
            $table->foreignId('zone_recipe_instance_id')->nullable()->constrained('zone_recipe_instances')->nullOnDelete();
            $table->string('status')->default('PLANNED'); // PLANNED|RUNNING|PAUSED|HARVESTED|ABORTED
            $table->timestamp('started_at')->nullable(); // посадка
            $table->timestamp('recipe_started_at')->nullable(); // старт автоматики/фаз
            $table->timestamp('expected_harvest_at')->nullable();
            $table->timestamp('actual_harvest_at')->nullable();
            $table->string('batch_label')->nullable();
            $table->text('notes')->nullable();
            $table->jsonb('settings')->nullable(); // плотность, количество кустов, субстрат, etc
            $table->timestamps();

            // Индексы для быстрого поиска
            $table->index('greenhouse_id', 'grow_cycles_greenhouse_id_idx');
            $table->index('zone_id', 'grow_cycles_zone_id_idx');
            $table->index('status', 'grow_cycles_status_idx');
            $table->index(['zone_id', 'status'], 'grow_cycles_zone_status_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('grow_cycles');
    }
};

