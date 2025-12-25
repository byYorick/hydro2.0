<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Обновление grow_cycles для ссылок на снапшоты вместо шаблонов.
     * current_phase_id и current_step_id теперь ссылаются на grow_cycle_phases и grow_cycle_phase_steps.
     */
    public function up(): void
    {
        Schema::table('grow_cycles', function (Blueprint $table) {
            // Удаляем старые FK на шаблоны (если они существуют)
            if (Schema::hasColumn('grow_cycles', 'current_phase_id')) {
                // Проверяем, существует ли FK constraint
                $constraintName = $this->getForeignKeyName('grow_cycles', 'current_phase_id');
                if ($constraintName) {
                    $table->dropForeign([$constraintName]);
                }
                $table->dropColumn('current_phase_id');
            }
            
            if (Schema::hasColumn('grow_cycles', 'current_step_id')) {
                $constraintName = $this->getForeignKeyName('grow_cycles', 'current_step_id');
                if ($constraintName) {
                    $table->dropForeign([$constraintName]);
                }
                $table->dropColumn('current_step_id');
            }
        });
        
        Schema::table('grow_cycles', function (Blueprint $table) {
            // Добавляем новые FK на снапшоты
            if (!Schema::hasColumn('grow_cycles', 'current_phase_id')) {
                $table->foreignId('current_phase_id')
                    ->nullable()
                    ->after('recipe_revision_id')
                    ->constrained('grow_cycle_phases')
                    ->nullOnDelete();
            }
            
            if (!Schema::hasColumn('grow_cycles', 'current_step_id')) {
                $table->foreignId('current_step_id')
                    ->nullable()
                    ->after('current_phase_id')
                    ->constrained('grow_cycle_phase_steps')
                    ->nullOnDelete();
            }
        });
        
        // Добавляем индексы для быстрого поиска
        Schema::table('grow_cycles', function (Blueprint $table) {
            if (!Schema::hasIndex('grow_cycles', 'grow_cycles_current_phase_idx')) {
                $table->index('current_phase_id', 'grow_cycles_current_phase_idx');
            }
            if (!Schema::hasIndex('grow_cycles', 'grow_cycles_current_step_idx')) {
                $table->index('current_step_id', 'grow_cycles_current_step_idx');
            }
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('grow_cycles', function (Blueprint $table) {
            // Удаляем FK на снапшоты
            if (Schema::hasColumn('grow_cycles', 'current_phase_id')) {
                $constraintName = $this->getForeignKeyName('grow_cycles', 'current_phase_id');
                if ($constraintName) {
                    $table->dropForeign([$constraintName]);
                }
                $table->dropColumn('current_phase_id');
            }
            
            if (Schema::hasColumn('grow_cycles', 'current_step_id')) {
                $constraintName = $this->getForeignKeyName('grow_cycles', 'current_step_id');
                if ($constraintName) {
                    $table->dropForeign([$constraintName]);
                }
                $table->dropColumn('current_step_id');
            }
        });
        
        Schema::table('grow_cycles', function (Blueprint $table) {
            // Восстанавливаем FK на шаблоны (для rollback)
            if (!Schema::hasColumn('grow_cycles', 'current_phase_id')) {
                $table->foreignId('current_phase_id')
                    ->nullable()
                    ->after('recipe_revision_id')
                    ->constrained('recipe_revision_phases')
                    ->nullOnDelete();
            }
            
            if (!Schema::hasColumn('grow_cycles', 'current_step_id')) {
                $table->foreignId('current_step_id')
                    ->nullable()
                    ->after('current_phase_id')
                    ->constrained('recipe_revision_phase_steps')
                    ->nullOnDelete();
            }
        });
    }
    
    /**
     * Получить имя FK constraint для колонки
     */
    private function getForeignKeyName(string $table, string $column): ?string
    {
        $constraints = DB::select("
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = ? 
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name IN (
                SELECT constraint_name
                FROM information_schema.key_column_usage
                WHERE table_name = ? AND column_name = ?
            )
        ", [$table, $table, $column]);
        
        return $constraints[0]->constraint_name ?? null;
    }
};

