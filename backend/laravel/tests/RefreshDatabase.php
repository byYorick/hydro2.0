<?php

namespace Tests;

use Illuminate\Foundation\Testing\RefreshDatabase as BaseRefreshDatabase;
use Illuminate\Support\Facades\DB;

trait RefreshDatabase
{
    use BaseRefreshDatabase {
        migrateDatabases as baseMigrateDatabases;
    }

    protected function migrateDatabases(): void
    {
        $this->dropTimescaleHypertables();
        $this->baseMigrateDatabases();
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

        if (!$exists || !$exists->exists) {
            return;
        }

        try {
            $hypertables = DB::select("
                SELECT hypertable_name
                FROM timescaledb_information.hypertables
                WHERE schema_name = 'public'
            ");
        } catch (\Throwable $e) {
            return;
        }

        foreach ($hypertables as $hypertable) {
            $name = $hypertable->hypertable_name ?? null;

            if (!$name) {
                continue;
            }

            try {
                DB::statement("SELECT drop_hypertable('{$name}', if_exists => TRUE, cascade_to_materializations => TRUE);");
            } catch (\Throwable $e) {
            }
        }
    }
}
