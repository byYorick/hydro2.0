<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        $uniqueIndexExists = DB::selectOne(<<<'SQL'
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'nodes'
                AND indexname = 'nodes_zone_unique'
            ) as exists
        SQL);

        if ($uniqueIndexExists && $uniqueIndexExists->exists) {
            DB::statement('DROP INDEX IF EXISTS nodes_zone_unique');
        }

        $indexExists = DB::selectOne(<<<'SQL'
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'nodes'
                AND indexname = 'nodes_zone_idx'
            ) as exists
        SQL);

        if (! $indexExists || ! $indexExists->exists) {
            Schema::table('nodes', function (Blueprint $table) {
                $table->index('zone_id', 'nodes_zone_idx');
            });
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        $indexExists = DB::selectOne(<<<'SQL'
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'nodes'
                AND indexname = 'nodes_zone_idx'
            ) as exists
        SQL);

        if ($indexExists && $indexExists->exists) {
            Schema::table('nodes', function (Blueprint $table) {
                $table->dropIndex('nodes_zone_idx');
            });
        }

        $uniqueIndexExists = DB::selectOne(<<<'SQL'
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'nodes'
                AND indexname = 'nodes_zone_unique'
            ) as exists
        SQL);

        if (! $uniqueIndexExists || ! $uniqueIndexExists->exists) {
            DB::statement(<<<'SQL'
                CREATE UNIQUE INDEX nodes_zone_unique
                ON nodes(zone_id)
                WHERE zone_id IS NOT NULL
            SQL);
        }
    }
};
