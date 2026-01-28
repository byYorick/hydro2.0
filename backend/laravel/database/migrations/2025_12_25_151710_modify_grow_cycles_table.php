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
            
            // Удаляем старые поля stage (заменены на current_phase_id/current_step_id)
            if (Schema::hasColumn('grow_cycles', 'current_stage_code')) {
                $table->dropIndex('grow_cycles_current_stage_code_idx');
                $table->dropColumn('current_stage_code');
            }
            if (Schema::hasColumn('grow_cycles', 'current_stage_started_at')) {
                $table->dropColumn('current_stage_started_at');
            }
        });
        
        Schema::table('grow_cycles', function (Blueprint $table) {
            // Добавляем связь с ревизией рецепта (NOT NULL - обязательно)
            if (!Schema::hasColumn('grow_cycles', 'recipe_revision_id')) {
                $table->foreignId('recipe_revision_id')->after('recipe_id')->constrained('recipe_revisions')->cascadeOnDelete();
            }
        });
        
        // Убеждаемся, что recipe_revision_id NOT NULL (если колонка уже существует и nullable)
        if (Schema::hasColumn('grow_cycles', 'recipe_revision_id')) {
            DB::statement('ALTER TABLE grow_cycles ALTER COLUMN recipe_revision_id SET NOT NULL');
        }
        
        Schema::table('grow_cycles', function (Blueprint $table) {
            
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
     * 
     * ВНИМАНИЕ: При rollback таблица zone_recipe_instances должна быть восстановлена
     * миграцией drop_legacy_tables (которая выполнится позже в обратном порядке).
     */
    public function down(): void
    {
        Schema::table('grow_cycles', function (Blueprint $table) {
            // Удаляем новые foreign keys
            if (Schema::hasColumn('grow_cycles', 'recipe_revision_id')) {
                $table->dropForeign(['recipe_revision_id']);
            }
            if (Schema::hasColumn('grow_cycles', 'current_phase_id')) {
                $table->dropForeign(['current_phase_id']);
            }
            if (Schema::hasColumn('grow_cycles', 'current_step_id')) {
                $table->dropForeign(['current_step_id']);
            }
            
            // Удаляем новые колонки
            $columnsToDrop = [];
            foreach (['recipe_revision_id', 'current_phase_id', 'current_step_id', 'planting_at', 'phase_started_at', 'step_started_at', 'progress_meta'] as $col) {
                if (Schema::hasColumn('grow_cycles', $col)) {
                    $columnsToDrop[] = $col;
                }
            }
            if (!empty($columnsToDrop)) {
                $table->dropColumn($columnsToDrop);
            }
        });
        
            // Восстанавливаем legacy поля только если таблица zone_recipe_instances существует
            // (она будет восстановлена миграцией drop_legacy_tables при полном rollback)
            if (Schema::hasTable('zone_recipe_instances')) {
                Schema::table('grow_cycles', function (Blueprint $table) {
                    if (!Schema::hasColumn('grow_cycles', 'zone_recipe_instance_id')) {
                        $table->foreignId('zone_recipe_instance_id')->nullable()->constrained('zone_recipe_instances')->nullOnDelete();
                    }
                });
            }
            
            // Восстанавливаем старые поля stage (для rollback совместимости)
            Schema::table('grow_cycles', function (Blueprint $table) {
                if (!Schema::hasColumn('grow_cycles', 'current_stage_code')) {
                    $table->string('current_stage_code', 64)->nullable()->after('status');
                }
                if (!Schema::hasColumn('grow_cycles', 'current_stage_started_at')) {
                    $table->timestamp('current_stage_started_at')->nullable()->after('current_stage_code');
                }
                // Восстанавливаем индекс
                if (!Schema::hasIndex('grow_cycles', 'grow_cycles_current_stage_code_idx')) {
                    $table->index('current_stage_code', 'grow_cycles_current_stage_code_idx');
                }
            });
    }
};

