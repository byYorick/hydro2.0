<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        if (
            $this->tableExists('commands')
            && $this->columnExists('commands', 'status')
            && $this->columnExists('commands', 'updated_at')
            && ! $this->indexExists('commands', 'commands_status_updated_at_idx')
        ) {
            DB::statement(
                'CREATE INDEX commands_status_updated_at_idx ON commands (status, updated_at DESC)'
            );
        }

        if (
            $this->tableExists('telemetry_last')
            && $this->columnExists('telemetry_last', 'sensor_id')
            && $this->columnExists('telemetry_last', 'updated_at')
            && ! $this->indexExists('telemetry_last', 'telemetry_last_sensor_updated_at_idx')
        ) {
            DB::statement(
                'CREATE INDEX telemetry_last_sensor_updated_at_idx ON telemetry_last (sensor_id, updated_at DESC)'
            );
        }
    }

    public function down(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        DB::statement('DROP INDEX IF EXISTS telemetry_last_sensor_updated_at_idx');
        DB::statement('DROP INDEX IF EXISTS commands_status_updated_at_idx');
    }

    private function tableExists(string $table): bool
    {
        $result = DB::selectOne(
            "
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = ?
            ) as exists
            ",
            [$table]
        );

        return (bool) ($result->exists ?? false);
    }

    private function columnExists(string $table, string $column): bool
    {
        $result = DB::selectOne(
            "
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = ? AND column_name = ?
            ) as exists
            ",
            [$table, $column]
        );

        return (bool) ($result->exists ?? false);
    }

    private function indexExists(string $table, string $indexName): bool
    {
        $result = DB::selectOne(
            "
            SELECT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE tablename = ? AND indexname = ?
            ) as exists
            ",
            [$table, $indexName]
        );

        return (bool) ($result->exists ?? false);
    }
};
