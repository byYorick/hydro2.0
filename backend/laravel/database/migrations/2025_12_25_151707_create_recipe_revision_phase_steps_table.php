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
            $table->jsonb('targets_override')->nullable(); // Перекрытие targets для этого подшага
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

