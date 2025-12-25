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
     * Добавление ограничений целостности:
     * - Уникальность активного цикла на зону (RUNNING/PAUSED)
     * - Enforce "1 node = 1 zone"
     */
    public function up(): void
    {
        // Частичный уникальный индекс для активного цикла на зону
        // Только один RUNNING или PAUSED цикл может быть в зоне одновременно
        DB::statement('
            CREATE UNIQUE INDEX grow_cycles_zone_active_unique 
            ON grow_cycles(zone_id) 
            WHERE status IN (\'RUNNING\', \'PAUSED\')
        ');
        
        // Опционально: ограничить 1 PLANNED цикл на зону
        // DB::statement('
        //     CREATE UNIQUE INDEX grow_cycles_zone_planned_unique 
        //     ON grow_cycles(zone_id) 
        //     WHERE status = \'PLANNED\'
        // ');
        
        // Enforce "1 node = 1 zone" - частичный уникальный индекс
        // Только один нода может быть привязан к одной зоне
        DB::statement('
            CREATE UNIQUE INDEX nodes_zone_unique 
            ON nodes(zone_id) 
            WHERE zone_id IS NOT NULL
        ');
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        DB::statement('DROP INDEX IF EXISTS grow_cycles_zone_active_unique');
        DB::statement('DROP INDEX IF EXISTS grow_cycles_zone_planned_unique');
        DB::statement('DROP INDEX IF EXISTS nodes_zone_unique');
    }
};

