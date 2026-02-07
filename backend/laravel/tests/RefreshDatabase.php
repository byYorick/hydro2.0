<?php

namespace Tests;

use Illuminate\Database\QueryException;
use Illuminate\Foundation\Testing\RefreshDatabase as BaseRefreshDatabase;
use Illuminate\Support\Facades\DB;
use Throwable;

trait RefreshDatabase
{
    use BaseRefreshDatabase {
        migrateDatabases as baseMigrateDatabases;
    }

    private const MIGRATION_MAX_RETRIES = 3;

    protected function migrateDatabases(): void
    {
        $attempt = 0;

        while (true) {
            try {
                $this->terminateStalePostgresConnections();
                $this->dropTimescaleHypertables();
                $this->baseMigrateDatabases();

                return;
            } catch (Throwable $exception) {
                $attempt++;

                if (! $this->isRetryableMigrationException($exception) || $attempt >= self::MIGRATION_MAX_RETRIES) {
                    throw $exception;
                }

                DB::disconnect();
                usleep($attempt * 250_000);
            }
        }
    }

    protected function dropTimescaleHypertables(): void
    {
        $connection = DB::connection();

        if ($connection->getDriverName() !== 'pgsql') {
            return;
        }

        try {
            $exists = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
                ) as exists
            ");
        } catch (\Throwable $e) {
            return;
        }

        if (! $exists || ! $exists->exists) {
            return;
        }

        try {
            $dropFunctionExists = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM pg_proc WHERE proname = 'drop_hypertable'
                ) as exists
            ");
        } catch (\Throwable $e) {
            return;
        }

        if (! $dropFunctionExists || ! $dropFunctionExists->exists) {
            return;
        }

        try {
            $schemaColumn = DB::selectOne("
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'timescaledb_information'
                  AND table_name = 'hypertables'
                  AND column_name IN ('schema_name', 'hypertable_schema')
                ORDER BY CASE column_name
                    WHEN 'hypertable_schema' THEN 1
                    ELSE 2
                END
                LIMIT 1
            ");
        } catch (\Throwable $e) {
            return;
        }

        if (! $schemaColumn || ! $schemaColumn->column_name) {
            return;
        }

        $column = $schemaColumn->column_name;

        try {
            $hypertables = DB::select("
                SELECT hypertable_name
                FROM timescaledb_information.hypertables
                WHERE {$column} = 'public'
            ");
        } catch (\Throwable $e) {
            return;
        }

        foreach ($hypertables as $hypertable) {
            $name = $hypertable->hypertable_name ?? null;

            if (! $name) {
                continue;
            }

            try {
                DB::statement("SELECT drop_hypertable('{$name}'::regclass, if_exists => TRUE, cascade_to_materializations => TRUE);");
            } catch (\Throwable $e) {
                try {
                    DB::statement("SELECT drop_hypertable('{$name}'::regclass, if_exists => TRUE);");
                } catch (\Throwable $e) {
                }
            }
        }
    }

    protected function terminateStalePostgresConnections(): void
    {
        $connection = DB::connection();

        if ($connection->getDriverName() !== 'pgsql') {
            return;
        }

        try {
            DB::statement("
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid <> pg_backend_pid()
            ");
        } catch (Throwable $e) {
            // Ignore failures; retry logic in migrateDatabases will handle transient issues.
        }
    }

    protected function isRetryableMigrationException(Throwable $exception): bool
    {
        if (! $exception instanceof QueryException) {
            return false;
        }

        $sqlState = $exception->getCode();
        if ($sqlState === '40P01' || $sqlState === '55P03') {
            return true;
        }

        $message = strtolower($exception->getMessage());

        return str_contains($message, 'deadlock detected')
            || str_contains($message, 'could not obtain lock')
            || str_contains($message, 'lock timeout');
    }
}
