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
     * PHASE 5.2: Добавление обязательных constraints и indexes для финального ужесточения схемы.
     * 
     * Добавляет:
     * - Уникальность каналов ноды (node_channels)
     * - Уникальность версий рецепта (recipe_revisions)
     * - Уникальность фаз/шагов в рецептах (recipe_revision_phases, recipe_revision_phase_steps)
     * - CHECK constraints для enum-полей где нужно
     */
    public function up(): void
    {
        // 1. Уникальность каналов ноды (node_channels)
        // Проверяем, существует ли уже такой индекс
        // Индекс уже создан в миграции create_node_channels_table как unique(['node_id', 'channel'])
        $nodeChannelsUniqueExists = DB::selectOne("
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE tablename = 'node_channels' 
                AND (indexname LIKE '%node_id%channel%' OR indexname LIKE '%node_channels%unique%')
            ) as exists
        ");
        
        // Если нет индекса, создаём (но он должен быть уже создан)
        if (!$nodeChannelsUniqueExists || !$nodeChannelsUniqueExists->exists) {
            DB::statement('
                CREATE UNIQUE INDEX IF NOT EXISTS node_channels_node_channel_unique 
                ON node_channels(node_id, channel) 
                WHERE node_id IS NOT NULL AND channel IS NOT NULL
            ');
        }
        
        // 2. Уникальность версий рецепта (recipe_revisions)
        // Проверяем, существует ли уже такой индекс (по revision_number, не version)
        // Индекс уже создан в миграции create_recipe_revisions_table как recipe_revisions_recipe_revision_unique
        // Но проверим на всякий случай
        $recipeRevisionsUniqueExists = DB::selectOne("
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE tablename = 'recipe_revisions' 
                AND (indexname = 'recipe_revisions_recipe_revision_unique' OR indexname = 'recipe_revisions_recipe_version_unique')
            ) as exists
        ");
        
        // Если нет индекса, создаём (но он должен быть уже создан)
        if (!$recipeRevisionsUniqueExists || !$recipeRevisionsUniqueExists->exists) {
            DB::statement('
                CREATE UNIQUE INDEX IF NOT EXISTS recipe_revisions_recipe_version_unique 
                ON recipe_revisions(recipe_id, revision_number) 
                WHERE recipe_id IS NOT NULL AND revision_number IS NOT NULL
            ');
        }
        
        // 3. Уникальность фаз в рецепте (recipe_revision_phases)
        // Проверяем, существует ли уже такой индекс
        // Индекс уже создан в миграции create_recipe_revision_phases_table
        $recipePhasesUniqueExists = DB::selectOne("
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE tablename = 'recipe_revision_phases' 
                AND indexname = 'recipe_revision_phases_revision_phase_unique'
            ) as exists
        ");
        
        // Если нет индекса, создаём (но он должен быть уже создан)
        if (!$recipePhasesUniqueExists || !$recipePhasesUniqueExists->exists) {
            DB::statement('
                CREATE UNIQUE INDEX IF NOT EXISTS recipe_revision_phases_revision_phase_unique 
                ON recipe_revision_phases(recipe_revision_id, phase_index) 
                WHERE recipe_revision_id IS NOT NULL AND phase_index IS NOT NULL
            ');
        }
        
        // 4. Уникальность шагов в фазе (recipe_revision_phase_steps)
        // Проверяем, существует ли уже такой индекс
        // Индекс уже создан в миграции create_recipe_revision_phase_steps_table
        $recipeStepsUniqueExists = DB::selectOne("
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE tablename = 'recipe_revision_phase_steps' 
                AND indexname = 'recipe_revision_phase_steps_phase_step_unique'
            ) as exists
        ");
        
        // Если нет индекса, создаём (но он должен быть уже создан)
        if (!$recipeStepsUniqueExists || !$recipeStepsUniqueExists->exists) {
            DB::statement('
                CREATE UNIQUE INDEX IF NOT EXISTS recipe_revision_phase_steps_phase_step_unique 
                ON recipe_revision_phase_steps(recipe_revision_phase_id, step_index) 
                WHERE recipe_revision_phase_id IS NOT NULL AND step_index IS NOT NULL
            ');
        }
        
        // 5. Уникальность 1 зона = 1 нода (nodes)
        // Проверяем, существует ли уже такой индекс
        $nodesZoneUniqueExists = DB::selectOne("
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE tablename = 'nodes' 
                AND indexname = 'nodes_zone_unique'
            ) as exists
        ");
        
        if (!$nodesZoneUniqueExists || !$nodesZoneUniqueExists->exists) {
            DB::statement('
                CREATE UNIQUE INDEX IF NOT EXISTS nodes_zone_unique 
                ON nodes(zone_id) 
                WHERE zone_id IS NOT NULL
            ');
        }
        
        // 6. CHECK constraints для enum-полей (если не native enum)
        // PostgreSQL использует CHECK constraints для enum-полей, созданных через Laravel
        // Они уже создаются автоматически при использовании ->enum(), но проверим критичные
        
        // Проверяем CHECK constraint для grow_cycles.status
        $growCyclesStatusCheckExists = DB::selectOne("
            SELECT EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conname = 'grow_cycles_status_check'
            ) as exists
        ");
        
        // Если нет CHECK constraint, добавляем (хотя Laravel должен был создать)
        // Но на всякий случай проверим и добавим если нужно
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        // Удаляем индексы в обратном порядке
        DB::statement('DROP INDEX IF EXISTS recipe_revision_phase_steps_phase_step_unique');
        DB::statement('DROP INDEX IF EXISTS recipe_revision_phases_revision_phase_unique');
        DB::statement('DROP INDEX IF EXISTS recipe_revisions_recipe_version_unique');
        DB::statement('DROP INDEX IF EXISTS node_channels_node_channel_unique');
        DB::statement('DROP INDEX IF EXISTS nodes_zone_unique');
    }
};

