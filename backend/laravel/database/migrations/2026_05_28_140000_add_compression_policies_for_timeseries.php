<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Schema;

/**
 * S3 (AUDIT_2026_05_28_BUGFIX_PLAN.md): включение Timescale compression
 * на больших временных таблицах, которые ранее имели только retention.
 *
 * Контекст:
 *   - `telemetry_samples`  — retention 90 дней, без compression → диск растёт
 *     линейно при production-кадансе телеметрии 2 сек.
 *   - `commands`           — retention 365 дней, без compression → каждый
 *     ack-update создаёт версию строки.
 *   - `zone_events`        — retention 365 дней, без compression.
 *
 *   `telemetry_agg_1h` сознательно **не** сжимаем: см. комментарий
 *   в `2026_04_23_120000_extend_telemetry_aggregates_for_ml.php` —
 *   часовые агрегаты компактны, выигрыш минимален, добавляет overhead.
 *
 *   `telemetry_agg_1m` и `zone_features_5m` — compression уже настроена
 *   соответствующими миграциями (`2026_04_23_120000_*` и
 *   `2026_04_23_130000_*`), здесь не дублируем.
 *
 *   ⚠ `telemetry_samples` в части dev-окружений утратила hypertable
 *   статус после destructive миграции `2025_12_25_151719_create_telemetry_
 *   samples_table.php` (DROP + CREATE без последующего `create_hypertable`).
 *   Если флаг `ensure_hypertable=true` — миграция попытается восстановить
 *   hypertable перед compression.
 *
 *   `commands` и `zone_events` используют **native PostgreSQL partitioning**
 *   (см. `2025_12_25_152231_add_partitioning_and_retention_*`), которое
 *   несовместимо с Timescale hypertable compression. Для них миграция
 *   логирует skip — compression возможна только при переводе на hypertable
 *   (отдельная задача, не in scope этого этапа).
 *
 * Стратегия:
 *   1. (Опционально) Если `ensure_hypertable=true` и таблица существует, но
 *      не hypertable — пытаемся `create_hypertable(... if_not_exists)`.
 *   2. Проверяем что таблица — hypertable (`timescaledb_information.hypertables`).
 *   3. Включаем compression с `compress_segmentby='zone_id'` (типичный
 *      query pattern — фильтры по зоне) — идемпотентно.
 *   4. Проверяем что compression policy ещё не существует, и добавляем
 *      с `if_not_exists => TRUE`.
 *
 * Совместимость:
 *   - Пропускается в `testing` (CI/local PHPUnit), где Timescale обычно
 *     не активна.
 *   - Пропускается в SQLite / non-Postgres драйверах.
 *   - Ошибки логируются как warning; миграция не падает — Timescale может
 *     отсутствовать на отдельных стендах.
 */
return new class extends Migration
{
    /**
     * Конфигурация compression policy.
     *
     * `ensure_hypertable` запускает `create_hypertable(... if_not_exists)`
     * для таблиц, которые должны быть hypertable, но потеряли этот статус
     * после destructive миграций (см. `telemetry_samples`).
     *
     * @var array<int, array{table: string, segmentby: string, compress_after: string, ensure_hypertable: bool, time_column: ?string, chunk_interval: ?string}>
     */
    private array $targets = [
        [
            'table' => 'telemetry_samples',
            'segmentby' => 'zone_id',
            'compress_after' => '7 days',
            'ensure_hypertable' => true,
            'time_column' => 'ts',
            'chunk_interval' => '1 day',
        ],
        [
            'table' => 'commands',
            'segmentby' => 'zone_id',
            'compress_after' => '7 days',
            // Native partitioning несовместимо с Timescale hypertable.
            'ensure_hypertable' => false,
            'time_column' => null,
            'chunk_interval' => null,
        ],
        [
            'table' => 'zone_events',
            'segmentby' => 'zone_id',
            'compress_after' => '30 days',
            // Native partitioning несовместимо с Timescale hypertable.
            'ensure_hypertable' => false,
            'time_column' => null,
            'chunk_interval' => null,
        ],
    ];

    public function up(): void
    {
        if (! $this->isTimescaleEnvironment()) {
            return;
        }

        foreach ($this->targets as $target) {
            $this->applyCompressionPolicy(
                table: $target['table'],
                segmentby: $target['segmentby'],
                compressAfter: $target['compress_after'],
                ensureHypertable: $target['ensure_hypertable'],
                timeColumn: $target['time_column'],
                chunkInterval: $target['chunk_interval'],
            );
        }
    }

    public function down(): void
    {
        if (! $this->isTimescaleEnvironment()) {
            return;
        }

        foreach ($this->targets as $target) {
            $table = $target['table'];

            try {
                DB::statement(
                    'SELECT remove_compression_policy(?, if_exists => TRUE)',
                    [$table]
                );
            } catch (\Exception $e) {
                Log::warning("S3 down: failed to remove compression policy on {$table}: ".$e->getMessage());
            }

            try {
                DB::statement("ALTER TABLE {$table} SET (timescaledb.compress = false)");
            } catch (\Exception $e) {
                // ignore — compression может быть уже не активна
            }
        }
    }

    private function isTimescaleEnvironment(): bool
    {
        if (app()->environment('testing')) {
            return false;
        }

        if (DB::getDriverName() !== 'pgsql') {
            return false;
        }

        return true;
    }

    private function applyCompressionPolicy(
        string $table,
        string $segmentby,
        string $compressAfter,
        bool $ensureHypertable,
        ?string $timeColumn,
        ?string $chunkInterval,
    ): void {
        try {
            if (! Schema::hasTable($table)) {
                Log::warning("S3: table {$table} does not exist, skipping compression policy");

                return;
            }

            // 1. (Опционально) Попытка восстановить hypertable, если она была
            //    потеряна destructive миграцией (см. telemetry_samples).
            if ($ensureHypertable && $timeColumn !== null && $chunkInterval !== null) {
                $this->ensureHypertable($table, $timeColumn, $chunkInterval);
            }

            $isHypertable = DB::selectOne(
                'SELECT EXISTS (
                    SELECT 1 FROM timescaledb_information.hypertables
                    WHERE hypertable_name = ?
                ) AS exists',
                [$table]
            );

            if (! $isHypertable || ! $isHypertable->exists) {
                Log::warning("S3: table {$table} is not a hypertable, skipping compression policy (probably native partitioning is used)");

                return;
            }

            // 2. Идемпотентно включаем compression. ALTER TABLE безопасен при
            //    повторном вызове с тем же segmentby.
            DB::statement(
                "ALTER TABLE {$table} SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = '{$segmentby}'
                )"
            );

            // 3. Проверяем что policy ещё не существует.
            $hasPolicy = DB::selectOne(
                "SELECT EXISTS (
                    SELECT 1 FROM timescaledb_information.jobs
                    WHERE proc_name = 'policy_compression'
                      AND hypertable_name = ?
                ) AS exists",
                [$table]
            );

            if ($hasPolicy && $hasPolicy->exists) {
                Log::info("S3: compression policy already exists on {$table}, skipping add_compression_policy");

                return;
            }

            // 4. Добавляем policy.
            DB::statement(
                "SELECT add_compression_policy(
                    ?,
                    INTERVAL '{$compressAfter}',
                    if_not_exists => TRUE
                )",
                [$table]
            );

            Log::info("S3: compression policy applied on {$table} (segmentby={$segmentby}, compress_after={$compressAfter})");
        } catch (\Exception $e) {
            Log::warning("S3: failed to apply compression policy on {$table}: ".$e->getMessage());
        }
    }

    /**
     * Восстановление hypertable status, если таблица его потеряла после
     * destructive миграции.
     *
     * Для `telemetry_samples` PK обязан включать time-column (`ts`), иначе
     * `create_hypertable` падает с ошибкой constraint exclusion. Если PK
     * не содержит time-column — пересоздаём его.
     */
    private function ensureHypertable(string $table, string $timeColumn, string $chunkInterval): void
    {
        try {
            $isHypertable = DB::selectOne(
                'SELECT EXISTS (
                    SELECT 1 FROM timescaledb_information.hypertables
                    WHERE hypertable_name = ?
                ) AS exists',
                [$table]
            );

            if ($isHypertable && $isHypertable->exists) {
                return;
            }

            Log::info("S3: ensuring hypertable for {$table} (timecolumn={$timeColumn}, chunk={$chunkInterval})");

            // Проверяем что PK содержит time-column. Для Timescale PK обязан
            // включать column партиционирования.
            $pkHasTime = DB::selectOne(
                'SELECT EXISTS (
                    SELECT 1
                    FROM pg_index i
                    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                    WHERE i.indrelid = ?::regclass
                      AND i.indisprimary
                      AND a.attname = ?
                ) AS exists',
                [$table, $timeColumn]
            );

            if (! $pkHasTime || ! $pkHasTime->exists) {
                Log::info("S3: rebuilding PK on {$table} to include {$timeColumn}");
                DB::statement("ALTER TABLE {$table} DROP CONSTRAINT IF EXISTS {$table}_pkey");
                DB::statement("ALTER TABLE {$table} ADD PRIMARY KEY (id, {$timeColumn})");
            }

            $rowCount = (int) DB::selectOne("SELECT COUNT(*) AS count FROM {$table}")->count;
            $migrateData = $rowCount > 0 ? 'true' : 'false';

            DB::statement(
                "SELECT create_hypertable(
                    ?,
                    ?,
                    chunk_time_interval => INTERVAL '{$chunkInterval}',
                    migrate_data => {$migrateData},
                    if_not_exists => TRUE
                )",
                [$table, $timeColumn]
            );

            Log::info("S3: hypertable created for {$table}");
        } catch (\Exception $e) {
            Log::warning("S3: failed to ensure hypertable for {$table}: ".$e->getMessage());
        }
    }
};
