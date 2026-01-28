<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Подшаги внутри фазы (опционально)
     * Например, в фазе "Вега" могут быть подшаги: "начало веги", "середина веги", "конец веги"
     */
    public function up(): void
    {
        Schema::create('recipe_revision_phase_steps', function (Blueprint $table) {
            $table->id();
            $table->foreignId('phase_id')->constrained('recipe_revision_phases')->cascadeOnDelete();
            $table->integer('step_index')->default(0); // Порядок подшага в фазе
            $table->string('name'); // Название подшага
            $table->integer('offset_hours')->default(0); // Смещение от начала фазы в часах
            $table->string('action')->nullable(); // Действие/задача подшага
            $table->text('description')->nullable();
            
            // Уставки по колонкам (те же что у фаз, nullable)
            $table->decimal('ph_target', 4, 2)->nullable();
            $table->decimal('ph_min', 4, 2)->nullable();
            $table->decimal('ph_max', 4, 2)->nullable();
            $table->decimal('ec_target', 5, 2)->nullable();
            $table->decimal('ec_min', 5, 2)->nullable();
            $table->decimal('ec_max', 5, 2)->nullable();
            $table->enum('irrigation_mode', ['SUBSTRATE', 'RECIRC'])->nullable();
            $table->integer('irrigation_interval_sec')->nullable();
            $table->integer('irrigation_duration_sec')->nullable();
            $table->integer('lighting_photoperiod_hours')->nullable();
            $table->time('lighting_start_time')->nullable();
            $table->integer('mist_interval_sec')->nullable();
            $table->integer('mist_duration_sec')->nullable();
            $table->enum('mist_mode', ['NORMAL', 'SPRAY'])->nullable();
            $table->decimal('temp_air_target', 5, 2)->nullable();
            $table->decimal('humidity_target', 5, 2)->nullable();
            $table->integer('co2_target')->nullable();
            
            $table->jsonb('extensions')->nullable(); // Только для расширений
            $table->timestamps();

            // Уникальность: одна фаза не может иметь два подшага с одинаковым индексом
            $table->unique(['phase_id', 'step_index'], 'recipe_revision_phase_steps_phase_step_unique');
            $table->index('phase_id', 'recipe_revision_phase_steps_phase_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('recipe_revision_phase_steps');
    }
};

