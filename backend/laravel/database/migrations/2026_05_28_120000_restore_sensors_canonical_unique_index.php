<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Восстанавливает canonical UNIQUE индекс на таблице sensors:
 *   (zone_id, node_id, scope, type, label)
 *
 * Миграция 2025_12_31_070152_add_unique_index_to_sensors_table.php дедуплицировала
 * существующие данные, но создание самого индекса было закомментировано
 * ("Skip creating index for now due to potential conflicts").
 *
 * Без этого индекса возможны дубли sensor identity, на которые ссылается
 * doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md §4.1 как на canonical guarantee.
 *
 * Стратегия:
 *  1) повторно дедуплицируем sensors (idempotent — если дублей нет, выполнится no-op);
 *  2) создаём индекс через `CREATE UNIQUE INDEX IF NOT EXISTS` (CONCURRENTLY,
 *     чтобы не блокировать запись на больших таблицах в production).
 *
 * `$withinTransaction = false` обязателен для CONCURRENTLY.
 */
return new class extends Migration
{
    public $withinTransaction = false;

    public function up(): void
    {
        if (! Schema::hasTable('sensors')) {
            return;
        }

        // Idempotent re-dedup на случай, если после 2025_12_31_070152 успели добавить дубли.
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

        // testing environment: создаём индекс обычным CREATE INDEX (без CONCURRENTLY) — SQLite/PG в CI быстрее и без отдельной транзакции.
        if (app()->environment('testing')) {
            DB::statement(
                'CREATE UNIQUE INDEX IF NOT EXISTS sensors_identity_unique_idx '
                .'ON sensors (zone_id, node_id, scope, type, label)'
            );

            return;
        }

        DB::statement(
            'CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS sensors_identity_unique_idx '
            .'ON sensors (zone_id, node_id, scope, type, label)'
        );
    }

    public function down(): void
    {
        if (app()->environment('testing')) {
            DB::statement('DROP INDEX IF EXISTS sensors_identity_unique_idx');

            return;
        }

        DB::statement('DROP INDEX CONCURRENTLY IF EXISTS sensors_identity_unique_idx');
    }
};
