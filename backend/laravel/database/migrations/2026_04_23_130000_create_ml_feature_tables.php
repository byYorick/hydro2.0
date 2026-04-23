<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * ML_FEATURE_PIPELINE Phase 2 — таблицы ML-витрин.
 *
 * - zone_features_5m         — wide view, строка на 5-мин окно × зону
 * - ml_labels                — таргеты прогноза (horizons 5/15/60 мин)
 * - ml_data_quality_windows  — окна, непригодные для обучения
 *
 * Owner: feature-builder (единственный writer для первых двух; последнюю
 * пишет также Laravel calibration flow и админ-UI — см. §5.8).
 *
 * См. doc_ai/09_AI_AND_DIGITAL_TWIN/ML_FEATURE_PIPELINE.md §5.2/§5.4/§5.8
 * + Приложение C.6 (денормализованные phase_code/phase_id).
 */
return new class extends Migration
{
    // create_hypertable требует commit, поэтому транзакция выключена.
    public $withinTransaction = false;

    public function up(): void
    {
        $this->createZoneFeatures5m();
        $this->createMlLabels();
        $this->createMlDataQualityWindows();
    }

    public function down(): void
    {
        // Порядок — обратный (DQ-окна не зависят от labels/features)
        Schema::dropIfExists('ml_data_quality_windows');
        Schema::dropIfExists('ml_labels');

        if (DB::getDriverName() === 'pgsql' && !app()->environment('testing')) {
            try {
                DB::statement("SELECT drop_hypertable('zone_features_5m', if_exists => TRUE)");
            } catch (\Exception $e) {
                // ignore
            }
        }
        Schema::dropIfExists('zone_features_5m');
    }

    private function createZoneFeatures5m(): void
    {
        DB::statement(<<<SQL
            CREATE TABLE zone_features_5m (
                ts                        timestamptz NOT NULL,
                zone_id                   bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,

                -- контекст эпизода (C.6: cycle_id FK + денормализованные phase_code/phase_id)
                cycle_id                  bigint      REFERENCES grow_cycles(id) ON DELETE SET NULL,
                phase_code                varchar(32),
                phase_id                  bigint,
                hours_since_cycle_start   double precision,
                hours_since_phase_start   double precision,
                hours_since_water_change  double precision,

                -- pH/EC
                ph_mean                   double precision,
                ph_std                    double precision,
                ph_slope                  double precision,
                ph_min                    double precision,
                ph_max                    double precision,
                ec_mean                   double precision,
                ec_std                    double precision,
                ec_slope                  double precision,
                ec_min                    double precision,
                ec_max                    double precision,

                -- раствор
                water_temp_mean           double precision,
                water_level_mean          double precision,

                -- внешние условия
                air_temp_mean             double precision,
                air_hum_mean              double precision,
                light_mean                double precision,
                co2_mean                  double precision,

                -- производные инженерные фичи (Phase 3 заполнит)
                ph_buffer_est             double precision,
                ec_consumption_rate       double precision,
                water_evaporation_rate    double precision,

                -- актуаторы: объёмы дозирования за окно 5 мин
                dose_ph_down_ml           double precision NOT NULL DEFAULT 0,
                dose_ph_up_ml             double precision NOT NULL DEFAULT 0,
                dose_npk_ml               double precision NOT NULL DEFAULT 0,
                dose_ca_ml                double precision NOT NULL DEFAULT 0,
                dose_mg_ml                double precision NOT NULL DEFAULT 0,
                dose_micro_ml             double precision NOT NULL DEFAULT 0,
                water_added_ml            double precision NOT NULL DEFAULT 0,

                -- качество данных
                valid_ratio               double precision,
                data_gap_seconds          integer,
                feature_schema_version    smallint NOT NULL DEFAULT 1,

                PRIMARY KEY (zone_id, ts)
            )
        SQL);

        DB::statement("CREATE INDEX zone_features_5m_ts_idx ON zone_features_5m (ts)");
        DB::statement("CREATE INDEX zone_features_5m_cycle_idx ON zone_features_5m (cycle_id, ts)");

        // Timescale hypertable + compression (>14 дней)
        if (DB::getDriverName() === 'pgsql' && !app()->environment('testing')) {
            try {
                DB::unprepared(<<<SQL
                    SELECT create_hypertable(
                        'zone_features_5m',
                        'ts',
                        chunk_time_interval => INTERVAL '7 days',
                        if_not_exists => TRUE
                    )
                SQL);

                DB::statement(<<<SQL
                    ALTER TABLE zone_features_5m SET (
                        timescaledb.compress,
                        timescaledb.compress_segmentby = 'zone_id'
                    )
                SQL);

                DB::statement(<<<SQL
                    SELECT add_compression_policy(
                        'zone_features_5m',
                        INTERVAL '14 days',
                        if_not_exists => TRUE
                    )
                SQL);
            } catch (\Exception $e) {
                \Log::warning('ML Phase 2: zone_features_5m hypertable/compression skipped: ' . $e->getMessage());
            }
        }
    }

    private function createMlLabels(): void
    {
        // ml_labels ОТДЕЛЬНО от zone_features_5m, чтобы исключить утечку
        // таргетов в фичи при обучении. См. §5.4 и §8 (point-in-time).
        DB::statement(<<<SQL
            CREATE TABLE ml_labels (
                ts                     timestamptz NOT NULL,
                zone_id                bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
                horizon_minutes        smallint    NOT NULL,

                ph_target              double precision,
                ec_target              double precision,
                ph_delta               double precision,
                ec_delta               double precision,

                is_valid               boolean     NOT NULL,
                invalid_reason         varchar(64),

                label_schema_version   smallint    NOT NULL DEFAULT 1,

                PRIMARY KEY (zone_id, ts, horizon_minutes),
                CONSTRAINT ml_labels_horizon_positive CHECK (horizon_minutes > 0)
            )
        SQL);

        DB::statement("CREATE INDEX ml_labels_ts_idx ON ml_labels (ts)");
        DB::statement("CREATE INDEX ml_labels_zone_horizon_idx ON ml_labels (zone_id, horizon_minutes, ts)");
    }

    private function createMlDataQualityWindows(): void
    {
        DB::statement(<<<SQL
            CREATE TABLE ml_data_quality_windows (
                id           bigserial   PRIMARY KEY,
                zone_id      bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
                start_ts     timestamptz NOT NULL,
                end_ts       timestamptz NOT NULL,
                reason       varchar(64) NOT NULL,
                severity     varchar(16) NOT NULL,
                details      jsonb,
                created_by   bigint      REFERENCES users(id) ON DELETE SET NULL,
                created_at   timestamptz NOT NULL DEFAULT now(),

                CONSTRAINT ml_dq_range_valid CHECK (end_ts > start_ts),
                CONSTRAINT ml_dq_severity_values CHECK (severity IN ('exclude', 'warn'))
            )
        SQL);

        DB::statement("CREATE INDEX ml_dq_zone_range_idx ON ml_data_quality_windows (zone_id, start_ts, end_ts)");
        DB::statement("CREATE INDEX ml_dq_reason_idx ON ml_data_quality_windows (reason)");
    }
};
