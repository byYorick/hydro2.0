<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Выравнивает Timescale retention policy для telemetry_samples с каноном
 * DATA_RETENTION_POLICY.md / Laravel telemetry:cleanup-raw / RETENTION_SAMPLES_DAYS = 30.
 *
 * Ранее миграция 2025_01_27_000007 ставила INTERVAL '90 days' — drift относительно app cleanup.
 */
return new class extends Migration
{
    public $withinTransaction = false;

    public function up(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        try {
            $hasTimescaleDB = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
                ) as exists;
            ");

            if (! $hasTimescaleDB || ! $hasTimescaleDB->exists) {
                Log::warning('TimescaleDB extension not found, skipping telemetry_samples retention align');

                return;
            }

            $isHypertable = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM timescaledb_information.hypertables
                    WHERE hypertable_name = 'telemetry_samples'
                ) as exists;
            ");

            if (! $isHypertable || ! $isHypertable->exists) {
                Log::info('telemetry_samples is not a hypertable, skipping retention align');

                return;
            }

            DB::statement("
                SELECT remove_retention_policy('telemetry_samples', if_exists => TRUE);
            ");

            DB::statement("
                SELECT add_retention_policy(
                    'telemetry_samples',
                    INTERVAL '30 days',
                    if_not_exists => TRUE
                );
            ");

            Log::info('Aligned telemetry_samples Timescale retention policy to 30 days');
        } catch (\Throwable $e) {
            Log::warning('Failed to align telemetry_samples retention policy: '.$e->getMessage());
        }
    }

    public function down(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        try {
            $hasTimescaleDB = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
                ) as exists;
            ");

            if (! $hasTimescaleDB || ! $hasTimescaleDB->exists) {
                return;
            }

            $isHypertable = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM timescaledb_information.hypertables
                    WHERE hypertable_name = 'telemetry_samples'
                ) as exists;
            ");

            if (! $isHypertable || ! $isHypertable->exists) {
                return;
            }

            DB::statement("
                SELECT remove_retention_policy('telemetry_samples', if_exists => TRUE);
            ");

            DB::statement("
                SELECT add_retention_policy(
                    'telemetry_samples',
                    INTERVAL '90 days',
                    if_not_exists => TRUE
                );
            ");

            Log::info('Restored telemetry_samples Timescale retention policy to 90 days');
        } catch (\Throwable $e) {
            Log::warning('Failed to restore telemetry_samples retention policy: '.$e->getMessage());
        }
    }
};
