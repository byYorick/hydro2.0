<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        if ($this->tableExists('commands')) {
            if (
                $this->columnExists('commands', 'status')
                && ! $this->indexExists('commands', 'commands_status_idx')
            ) {
                DB::statement('CREATE INDEX IF NOT EXISTS commands_status_idx ON commands (status)');
            }

            if (
                $this->columnExists('commands', 'cmd_id')
                && ! $this->indexExists('commands', 'commands_cmd_id_idx')
            ) {
                DB::statement('CREATE INDEX IF NOT EXISTS commands_cmd_id_idx ON commands (cmd_id)');
            }
        }

        if ($this->tableExists('zone_events')) {
            if (
                $this->columnExists('zone_events', 'zone_id')
                && $this->columnExists('zone_events', 'created_at')
                && ! $this->indexExists('zone_events', 'zone_events_zone_id_created_at_idx')
            ) {
                DB::statement('CREATE INDEX IF NOT EXISTS zone_events_zone_id_created_at_idx ON zone_events (zone_id, created_at)');
            }

            if (
                $this->columnExists('zone_events', 'type')
                && ! $this->indexExists('zone_events', 'zone_events_type_idx')
            ) {
                DB::statement('CREATE INDEX IF NOT EXISTS zone_events_type_idx ON zone_events (type)');
            }
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        DB::statement('DROP INDEX IF EXISTS zone_events_type_idx');
        DB::statement('DROP INDEX IF EXISTS zone_events_zone_id_created_at_idx');
        DB::statement('DROP INDEX IF EXISTS commands_cmd_id_idx');
        DB::statement('DROP INDEX IF EXISTS commands_status_idx');
    }

    /**
     * Проверка существования таблицы.
     */
    private function tableExists(string $table): bool
    {
        $result = DB::selectOne("
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = ?
            ) as exists
        ", [$table]);

        return $result && $result->exists;
    }

    /**
     * Проверка существования колонки.
     */
    private function columnExists(string $table, string $column): bool
    {
        $result = DB::selectOne("
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = ? AND column_name = ?
            ) as exists
        ", [$table, $column]);

        return $result && $result->exists;
    }

    /**
     * Проверка существования индекса.
     */
    private function indexExists(string $table, string $indexName): bool
    {
        $result = DB::selectOne("
            SELECT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE tablename = ? AND indexname = ?
            ) as exists
        ", [$table, $indexName]);

        return $result && $result->exists;
    }
};
