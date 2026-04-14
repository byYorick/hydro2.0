<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        // recipe_revision_phases — шаблон выбора стратегии advance
        if (Schema::hasTable('recipe_revision_phases')
            && ! Schema::hasColumn('recipe_revision_phases', 'phase_advance_strategy')) {
            Schema::table('recipe_revision_phases', function (Blueprint $table): void {
                $table->string('phase_advance_strategy', 32)
                    ->default('time')
                    ->after('progress_model');
            });
        }

        // grow_cycle_phases — snapshot стратегии для конкретного цикла
        if (Schema::hasTable('grow_cycle_phases')
            && ! Schema::hasColumn('grow_cycle_phases', 'phase_advance_strategy')) {
            Schema::table('grow_cycle_phases', function (Blueprint $table): void {
                $table->string('phase_advance_strategy', 32)
                    ->default('time')
                    ->after('progress_model');
            });
        }

        DB::statement("
            DO \$\$
            BEGIN
                ALTER TABLE recipe_revision_phases
                ADD CONSTRAINT recipe_revision_phases_advance_strategy_check
                CHECK (phase_advance_strategy IN ('time','gdd','dli','ai','manual_only'));
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END
            \$\$;
        ");

        DB::statement("
            DO \$\$
            BEGIN
                ALTER TABLE grow_cycle_phases
                ADD CONSTRAINT grow_cycle_phases_advance_strategy_check
                CHECK (phase_advance_strategy IN ('time','gdd','dli','ai','manual_only'));
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END
            \$\$;
        ");

        // Индекс для cron auto-advance: быстрый поиск running cycles по phase_started_at
        if (Schema::hasTable('grow_cycles')
            && ! $this->indexExists('grow_cycles', 'grow_cycles_status_phase_started_idx')) {
            Schema::table('grow_cycles', function (Blueprint $table): void {
                $table->index(['status', 'phase_started_at'], 'grow_cycles_status_phase_started_idx');
            });
        }
    }

    public function down(): void
    {
        DB::statement('ALTER TABLE recipe_revision_phases DROP CONSTRAINT IF EXISTS recipe_revision_phases_advance_strategy_check');
        DB::statement('ALTER TABLE grow_cycle_phases DROP CONSTRAINT IF EXISTS grow_cycle_phases_advance_strategy_check');

        if (Schema::hasTable('recipe_revision_phases') && Schema::hasColumn('recipe_revision_phases', 'phase_advance_strategy')) {
            Schema::table('recipe_revision_phases', function (Blueprint $table): void {
                $table->dropColumn('phase_advance_strategy');
            });
        }

        if (Schema::hasTable('grow_cycle_phases') && Schema::hasColumn('grow_cycle_phases', 'phase_advance_strategy')) {
            Schema::table('grow_cycle_phases', function (Blueprint $table): void {
                $table->dropColumn('phase_advance_strategy');
            });
        }

        if (Schema::hasTable('grow_cycles') && $this->indexExists('grow_cycles', 'grow_cycles_status_phase_started_idx')) {
            Schema::table('grow_cycles', function (Blueprint $table): void {
                $table->dropIndex('grow_cycles_status_phase_started_idx');
            });
        }
    }

    private function indexExists(string $table, string $indexName): bool
    {
        $row = DB::selectOne(
            'SELECT indexname FROM pg_indexes WHERE schemaname=current_schema() AND tablename = ? AND indexname = ?',
            [$table, $indexName],
        );

        return $row !== null;
    }
};
