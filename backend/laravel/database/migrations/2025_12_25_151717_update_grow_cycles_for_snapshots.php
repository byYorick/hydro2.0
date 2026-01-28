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
        // Удаляем старые FK на шаблоны (если они существуют)
        // Используем прямой SQL для более надежного удаления
        if (Schema::hasColumn('grow_cycles', 'current_phase_id')) {
            $constraintName = $this->getForeignKeyName('grow_cycles', 'current_phase_id');
            if ($constraintName) {
                DB::statement("ALTER TABLE grow_cycles DROP CONSTRAINT IF EXISTS {$constraintName}");
            }
            Schema::table('grow_cycles', function (Blueprint $table) {
                $table->dropColumn('current_phase_id');
            });
        }
        
        if (Schema::hasColumn('grow_cycles', 'current_step_id')) {
            $constraintName = $this->getForeignKeyName('grow_cycles', 'current_step_id');
            if ($constraintName) {
                DB::statement("ALTER TABLE grow_cycles DROP CONSTRAINT IF EXISTS {$constraintName}");
            }
            Schema::table('grow_cycles', function (Blueprint $table) {
                $table->dropColumn('current_step_id');
            });
        }
        
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
        try {
            $constraints = DB::select("
                SELECT tc.constraint_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu 
                    ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_name = ? 
                AND tc.constraint_type = 'FOREIGN KEY'
                AND kcu.column_name = ?
            ", [$table, $column]);
            
            return $constraints[0]->constraint_name ?? null;
        } catch (\Exception $e) {
            return null;
        }
    }
};

