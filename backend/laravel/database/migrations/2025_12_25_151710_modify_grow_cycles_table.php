<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Модификация grow_cycles для новой модели:
     * - Удалить zone_recipe_instance_id (legacy)
     * - Добавить recipe_revision_id (NOT NULL)
     * - Добавить current_phase_id, current_step_id
     * - Добавить временные метки и progress_meta
     */
    public function up(): void
    {
        Schema::table('grow_cycles', function (Blueprint $table) {
            // Удаляем legacy связь (если существует)
            if (Schema::hasColumn('grow_cycles', 'zone_recipe_instance_id')) {
                $table->dropForeign(['zone_recipe_instance_id']);
                $table->dropColumn('zone_recipe_instance_id');
            }
        });
        
        Schema::table('grow_cycles', function (Blueprint $table) {
            // Добавляем связь с ревизией рецепта (NOT NULL после заполнения данных)
            if (!Schema::hasColumn('grow_cycles', 'recipe_revision_id')) {
                $table->foreignId('recipe_revision_id')->nullable()->after('recipe_id')->constrained('recipe_revisions')->nullOnDelete();
            }
            
            // Текущая фаза и шаг
            if (!Schema::hasColumn('grow_cycles', 'current_phase_id')) {
                $table->foreignId('current_phase_id')->nullable()->after('recipe_revision_id')->constrained('recipe_revision_phases')->nullOnDelete();
            }
            if (!Schema::hasColumn('grow_cycles', 'current_step_id')) {
                $table->foreignId('current_step_id')->nullable()->after('current_phase_id')->constrained('recipe_revision_phase_steps')->nullOnDelete();
            }
            
            // Временные метки (проверяем существование перед добавлением)
            if (!Schema::hasColumn('grow_cycles', 'planting_at')) {
                $table->timestamp('planting_at')->nullable()->after('started_at'); // Посадка (может отличаться от started_at)
            }
            if (!Schema::hasColumn('grow_cycles', 'phase_started_at')) {
                $table->timestamp('phase_started_at')->nullable()->after('recipe_started_at'); // Когда началась текущая фаза
            }
            if (!Schema::hasColumn('grow_cycles', 'step_started_at')) {
                $table->timestamp('step_started_at')->nullable()->after('phase_started_at'); // Когда начался текущий шаг
            }
            
            // Метаданные прогресса (temp/light коррекции, computed_due_at, etc)
            if (!Schema::hasColumn('grow_cycles', 'progress_meta')) {
                $table->jsonb('progress_meta')->nullable()->after('settings');
            }
        });
        
        // После заполнения данных можно сделать recipe_revision_id NOT NULL
        // Но пока оставляем nullable для возможности миграции данных
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('grow_cycles', function (Blueprint $table) {
            $table->dropForeign(['recipe_revision_id']);
            $table->dropForeign(['current_phase_id']);
            $table->dropForeign(['current_step_id']);
            
            $table->dropColumn([
                'recipe_revision_id',
                'current_phase_id',
                'current_step_id',
                'planting_at',
                'phase_started_at',
                'step_started_at',
                'progress_meta',
            ]);
            
            // Восстанавливаем legacy поле (если нужно для rollback)
            $table->foreignId('zone_recipe_instance_id')->nullable()->constrained('zone_recipe_instances')->nullOnDelete();
        });
    }
};

