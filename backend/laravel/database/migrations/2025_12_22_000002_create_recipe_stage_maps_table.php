<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('recipe_stage_maps', function (Blueprint $table) {
            $table->id();
            $table->foreignId('recipe_id')->constrained('recipes')->cascadeOnDelete();
            $table->foreignId('stage_template_id')->constrained('grow_stage_templates')->cascadeOnDelete();
            $table->integer('order_index')->default(0); // Порядок стадий в рецепте
            $table->integer('start_offset_days')->nullable(); // Смещение начала стадии от посадки (в днях)
            $table->integer('end_offset_days')->nullable(); // Смещение конца стадии от посадки (в днях)
            $table->jsonb('phase_indices')->nullable(); // Массив индексов фаз рецепта [0, 1, 2] или phase_ids
            $table->jsonb('targets_override')->nullable(); // Перекрытие targets для стадии
            $table->timestamps();

            $table->index(['recipe_id', 'order_index'], 'recipe_stage_maps_recipe_order_idx');
            $table->index('stage_template_id', 'recipe_stage_maps_stage_template_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('recipe_stage_maps');
    }
};

