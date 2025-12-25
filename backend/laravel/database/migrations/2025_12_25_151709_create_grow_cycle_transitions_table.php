<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * История переходов фаз в цикле выращивания
     * Логирует все переходы: авто по времени, ручной switch, изменение рецепта
     */
    public function up(): void
    {
        Schema::create('grow_cycle_transitions', function (Blueprint $table) {
            $table->id();
            $table->foreignId('grow_cycle_id')->constrained('grow_cycles')->cascadeOnDelete();
            $table->foreignId('from_phase_id')->nullable()->constrained('recipe_revision_phases')->nullOnDelete();
            $table->foreignId('to_phase_id')->constrained('recipe_revision_phases')->nullOnDelete();
            $table->foreignId('from_step_id')->nullable()->constrained('recipe_revision_phase_steps')->nullOnDelete();
            $table->foreignId('to_step_id')->nullable()->constrained('recipe_revision_phase_steps')->nullOnDelete();
            $table->string('trigger_type'); // AUTO|MANUAL|RECIPE_CHANGE|SYSTEM
            $table->text('comment')->nullable(); // Комментарий (обязателен для MANUAL)
            $table->foreignId('triggered_by')->nullable()->constrained('users')->nullOnDelete();
            $table->jsonb('metadata')->nullable(); // Дополнительные данные (progress_meta snapshot, etc)
            $table->timestamps();

            // Индексы для истории переходов
            $table->index('grow_cycle_id', 'grow_cycle_transitions_cycle_idx');
            $table->index(['grow_cycle_id', 'created_at'], 'grow_cycle_transitions_cycle_created_idx');
            $table->index('trigger_type', 'grow_cycle_transitions_trigger_type_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('grow_cycle_transitions');
    }
};

