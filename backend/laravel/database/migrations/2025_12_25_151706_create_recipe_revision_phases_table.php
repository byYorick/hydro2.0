<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Фазы ревизии рецепта - целевые параметры по колонкам (не JSONB)
     * Каждая фаза имеет stage_template_id для UI отображения
     */
    public function up(): void
    {
        Schema::create('recipe_revision_phases', function (Blueprint $table) {
            $table->id();
            $table->foreignId('recipe_revision_id')->constrained('recipe_revisions')->cascadeOnDelete();
            $table->foreignId('stage_template_id')->nullable()->constrained('grow_stage_templates')->nullOnDelete();
            $table->integer('phase_index')->default(0); // Порядок фазы в рецепте (0, 1, 2...)
            $table->string('name'); // Название фазы
            
            // Обязательные параметры (MVP)
            $table->decimal('ph_target', 4, 2)->nullable();
            $table->decimal('ph_min', 4, 2)->nullable();
            $table->decimal('ph_max', 4, 2)->nullable();
            $table->decimal('ec_target', 5, 2)->nullable();
            $table->decimal('ec_min', 5, 2)->nullable();
            $table->decimal('ec_max', 5, 2)->nullable();
            $table->enum('irrigation_mode', ['SUBSTRATE', 'RECIRC'])->nullable();
            $table->integer('irrigation_interval_sec')->nullable();
            $table->integer('irrigation_duration_sec')->nullable();
            
            // Опциональные параметры
            $table->integer('lighting_photoperiod_hours')->nullable();
            $table->time('lighting_start_time')->nullable();
            $table->integer('mist_interval_sec')->nullable();
            $table->integer('mist_duration_sec')->nullable();
            $table->enum('mist_mode', ['NORMAL', 'SPRAY'])->nullable();
            $table->decimal('temp_air_target', 5, 2)->nullable(); // Запрос к климату теплицы
            $table->decimal('humidity_target', 5, 2)->nullable();
            $table->integer('co2_target')->nullable(); // ppm
            
            // Прогресс фазы
            $table->string('progress_model')->nullable(); // TIME|TIME_WITH_TEMP_CORRECTION|GDD|DLI
            $table->integer('duration_hours')->nullable();
            $table->integer('duration_days')->nullable();
            $table->decimal('base_temp_c', 4, 2)->nullable(); // Для GDD
            $table->decimal('target_gdd', 8, 2)->nullable(); // Градусо-дни
            $table->decimal('dli_target', 6, 2)->nullable(); // Daily Light Integral
            
            // Расширения (JSON только для нестандартных параметров)
            $table->jsonb('extensions')->nullable();
            
            $table->timestamps();

            // Уникальность: одна ревизия не может иметь две фазы с одинаковым индексом
            $table->unique(['recipe_revision_id', 'phase_index'], 'recipe_revision_phases_revision_phase_unique');
            $table->index('recipe_revision_id', 'recipe_revision_phases_revision_idx');
            $table->index('stage_template_id', 'recipe_revision_phases_stage_template_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('recipe_revision_phases');
    }
};

