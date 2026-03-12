<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('node_channels', function (Blueprint $table) {
            if (! Schema::hasColumn('node_channels', 'last_seen_at')) {
                $table->timestamp('last_seen_at')->nullable()->after('config');
                $table->index('last_seen_at', 'idx_node_channels_last_seen_at');
            }
            if (! Schema::hasColumn('node_channels', 'is_active')) {
                $table->boolean('is_active')->default(true)->after('last_seen_at');
                $table->index(['node_id', 'is_active'], 'idx_node_channels_node_active');
            }
        });

        Schema::create('pump_calibrations', function (Blueprint $table) {
            $table->id();
            $table->foreignId('node_channel_id')->constrained('node_channels')->cascadeOnDelete();
            $table->string('component', 64)->nullable();
            $table->decimal('ml_per_sec', 12, 6);
            $table->decimal('k_ms_per_ml_l', 12, 6)->nullable();
            $table->unsignedInteger('duration_sec')->nullable();
            $table->decimal('actual_ml', 12, 3)->nullable();
            $table->decimal('test_volume_l', 12, 3)->nullable();
            $table->decimal('ec_before_ms', 12, 6)->nullable();
            $table->decimal('ec_after_ms', 12, 6)->nullable();
            $table->decimal('delta_ec_ms', 12, 6)->nullable();
            $table->decimal('temperature_c', 12, 3)->nullable();
            $table->string('source', 64)->default('manual_calibration');
            $table->decimal('quality_score', 5, 2)->nullable();
            $table->unsignedInteger('sample_count')->default(1);
            $table->timestamp('valid_from')->useCurrent();
            $table->timestamp('valid_to')->nullable();
            $table->boolean('is_active')->default(true);
            $table->jsonb('meta')->nullable();
            $table->timestamps();

            $table->index(['node_channel_id', 'is_active'], 'idx_pump_calibration_node_active');
            $table->index(['node_channel_id', 'valid_from'], 'idx_pump_calibration_node_valid_from');
        });

        // Backfill текущих калибровок из legacy node_channels.config->pump_calibration.
        DB::statement(
            <<<'SQL'
            INSERT INTO pump_calibrations (
                node_channel_id,
                component,
                ml_per_sec,
                k_ms_per_ml_l,
                duration_sec,
                actual_ml,
                test_volume_l,
                ec_before_ms,
                ec_after_ms,
                delta_ec_ms,
                temperature_c,
                source,
                quality_score,
                sample_count,
                valid_from,
                is_active,
                meta,
                created_at,
                updated_at
            )
            SELECT
                nc.id AS node_channel_id,
                NULLIF(nc.config->'pump_calibration'->>'component', '') AS component,
                (nc.config->'pump_calibration'->>'ml_per_sec')::numeric(12,6) AS ml_per_sec,
                CASE
                    WHEN (nc.config->'pump_calibration'->>'k_ms_per_ml_l') ~ '^[0-9]+(\.[0-9]+)?$'
                        THEN (nc.config->'pump_calibration'->>'k_ms_per_ml_l')::numeric(12,6)
                    ELSE NULL
                END AS k_ms_per_ml_l,
                CASE
                    WHEN (nc.config->'pump_calibration'->>'duration_sec') ~ '^[0-9]+$'
                        THEN (nc.config->'pump_calibration'->>'duration_sec')::integer
                    ELSE NULL
                END AS duration_sec,
                CASE
                    WHEN (nc.config->'pump_calibration'->>'actual_ml') ~ '^[0-9]+(\.[0-9]+)?$'
                        THEN (nc.config->'pump_calibration'->>'actual_ml')::numeric(12,3)
                    ELSE NULL
                END AS actual_ml,
                CASE
                    WHEN (nc.config->'pump_calibration'->>'test_volume_l') ~ '^[0-9]+(\.[0-9]+)?$'
                        THEN (nc.config->'pump_calibration'->>'test_volume_l')::numeric(12,3)
                    ELSE NULL
                END AS test_volume_l,
                CASE
                    WHEN (nc.config->'pump_calibration'->>'ec_before_ms') ~ '^[0-9]+(\.[0-9]+)?$'
                        THEN (nc.config->'pump_calibration'->>'ec_before_ms')::numeric(12,6)
                    ELSE NULL
                END AS ec_before_ms,
                CASE
                    WHEN (nc.config->'pump_calibration'->>'ec_after_ms') ~ '^[0-9]+(\.[0-9]+)?$'
                        THEN (nc.config->'pump_calibration'->>'ec_after_ms')::numeric(12,6)
                    ELSE NULL
                END AS ec_after_ms,
                CASE
                    WHEN (nc.config->'pump_calibration'->>'delta_ec_ms') ~ '^[0-9]+(\.[0-9]+)?$'
                        THEN (nc.config->'pump_calibration'->>'delta_ec_ms')::numeric(12,6)
                    ELSE NULL
                END AS delta_ec_ms,
                CASE
                    WHEN (nc.config->'pump_calibration'->>'temperature_c') ~ '^[0-9]+(\.[0-9]+)?$'
                        THEN (nc.config->'pump_calibration'->>'temperature_c')::numeric(12,3)
                    ELSE NULL
                END AS temperature_c,
                'legacy_config_backfill' AS source,
                0.50 AS quality_score,
                1 AS sample_count,
                COALESCE(
                    NULLIF(nc.config->'pump_calibration'->>'calibrated_at', '')::timestamp,
                    NOW()
                ) AS valid_from,
                TRUE AS is_active,
                jsonb_build_object('migration', '2026_02_25_120000') AS meta,
                NOW(),
                NOW()
            FROM node_channels nc
            WHERE nc.config IS NOT NULL
              AND jsonb_typeof(nc.config->'pump_calibration') = 'object'
              AND (nc.config->'pump_calibration'->>'ml_per_sec') ~ '^[0-9]+(\.[0-9]+)?$'
              AND (nc.config->'pump_calibration'->>'ml_per_sec')::numeric > 0
            SQL
        );
    }

    public function down(): void
    {
        Schema::dropIfExists('pump_calibrations');

        Schema::table('node_channels', function (Blueprint $table) {
            if (Schema::hasColumn('node_channels', 'is_active')) {
                $table->dropIndex('idx_node_channels_node_active');
                $table->dropColumn('is_active');
            }
            if (Schema::hasColumn('node_channels', 'last_seen_at')) {
                $table->dropIndex('idx_node_channels_last_seen_at');
                $table->dropColumn('last_seen_at');
            }
        });
    }
};
