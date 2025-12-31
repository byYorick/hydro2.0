<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public bool $withinTransaction = false;

    /**
     * Run the migrations.
     */
    public function up(): void
    {
        DB::statement(
            <<<'SQL'
            WITH duplicates AS (
                SELECT MIN(id) AS keep_id,
                       ARRAY_AGG(id) AS ids
                FROM sensors
                GROUP BY zone_id, node_id, scope, type, label
                HAVING COUNT(*) > 1
            ),
            mapping AS (
                SELECT keep_id, unnest(ids) AS sensor_id
                FROM duplicates
            )
            UPDATE telemetry_samples ts
            SET sensor_id = mapping.keep_id
            FROM mapping
            WHERE ts.sensor_id = mapping.sensor_id
              AND mapping.sensor_id <> mapping.keep_id
            SQL
        );

        DB::statement(
            <<<'SQL'
            WITH duplicates AS (
                SELECT MIN(id) AS keep_id,
                       ARRAY_AGG(id) AS ids
                FROM sensors
                GROUP BY zone_id, node_id, scope, type, label
                HAVING COUNT(*) > 1
            ),
            mapping AS (
                SELECT keep_id, unnest(ids) AS sensor_id
                FROM duplicates
            ),
            ranked AS (
                SELECT
                    mapping.keep_id,
                    tl.last_value,
                    tl.last_ts,
                    tl.last_quality,
                    tl.updated_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY mapping.keep_id
                        ORDER BY tl.last_ts DESC NULLS LAST, tl.updated_at DESC NULLS LAST
                    ) AS rn
                FROM mapping
                JOIN telemetry_last tl ON tl.sensor_id = mapping.sensor_id
            )
            INSERT INTO telemetry_last (sensor_id, last_value, last_ts, last_quality, updated_at)
            SELECT keep_id, last_value, last_ts, last_quality, updated_at
            FROM ranked
            WHERE rn = 1
            ON CONFLICT (sensor_id) DO UPDATE SET
                last_value = EXCLUDED.last_value,
                last_ts = EXCLUDED.last_ts,
                last_quality = EXCLUDED.last_quality,
                updated_at = EXCLUDED.updated_at
            SQL
        );

        DB::statement(
            <<<'SQL'
            WITH duplicates AS (
                SELECT MIN(id) AS keep_id,
                       ARRAY_AGG(id) AS ids
                FROM sensors
                GROUP BY zone_id, node_id, scope, type, label
                HAVING COUNT(*) > 1
            ),
            mapping AS (
                SELECT keep_id, unnest(ids) AS sensor_id
                FROM duplicates
            )
            DELETE FROM telemetry_last tl
            USING mapping
            WHERE tl.sensor_id = mapping.sensor_id
              AND mapping.sensor_id <> mapping.keep_id
            SQL
        );

        DB::statement(
            <<<'SQL'
            WITH duplicates AS (
                SELECT MIN(id) AS keep_id,
                       ARRAY_AGG(id) AS ids
                FROM sensors
                GROUP BY zone_id, node_id, scope, type, label
                HAVING COUNT(*) > 1
            ),
            mapping AS (
                SELECT keep_id, unnest(ids) AS sensor_id
                FROM duplicates
            )
            DELETE FROM sensors s
            USING mapping
            WHERE s.id = mapping.sensor_id
              AND mapping.sensor_id <> mapping.keep_id
            SQL
        );

        DB::statement(
            'CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS sensors_identity_unique_idx ON sensors (zone_id, node_id, scope, type, label)'
        );
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        DB::statement('DROP INDEX CONCURRENTLY IF EXISTS sensors_identity_unique_idx');
    }
};
