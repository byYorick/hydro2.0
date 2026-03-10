<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('pump_calibrations', function (Blueprint $table) {
            if (! Schema::hasColumn('pump_calibrations', 'mode')) {
                $table->string('mode', 32)->default('generic')->after('component');
                $table->index(['node_channel_id', 'mode', 'is_active'], 'idx_pump_calibration_node_mode_active');
            }
            if (! Schema::hasColumn('pump_calibrations', 'min_effective_ml')) {
                $table->decimal('min_effective_ml', 12, 3)->nullable()->after('ml_per_sec');
            }
            if (! Schema::hasColumn('pump_calibrations', 'transport_delay_sec')) {
                $table->unsignedInteger('transport_delay_sec')->nullable()->after('test_volume_l');
            }
            if (! Schema::hasColumn('pump_calibrations', 'deadtime_sec')) {
                $table->unsignedInteger('deadtime_sec')->nullable()->after('transport_delay_sec');
            }
            if (! Schema::hasColumn('pump_calibrations', 'curve_points')) {
                $table->jsonb('curve_points')->nullable()->after('meta');
            }
        });

        if (! Schema::hasTable('zone_process_calibrations')) {
            Schema::create('zone_process_calibrations', function (Blueprint $table) {
                $table->id();
                $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
                $table->string('mode', 32)->default('generic');
                $table->decimal('ec_gain_per_ml', 12, 6)->nullable();
                $table->decimal('ph_up_gain_per_ml', 12, 6)->nullable();
                $table->decimal('ph_down_gain_per_ml', 12, 6)->nullable();
                $table->decimal('ph_per_ec_ml', 12, 6)->nullable();
                $table->decimal('ec_per_ph_ml', 12, 6)->nullable();
                $table->unsignedInteger('transport_delay_sec')->nullable();
                $table->unsignedInteger('settle_sec')->nullable();
                $table->decimal('confidence', 5, 2)->nullable();
                $table->string('source', 64)->default('manual');
                $table->timestamp('valid_from')->useCurrent();
                $table->timestamp('valid_to')->nullable();
                $table->boolean('is_active')->default(true);
                $table->jsonb('meta')->nullable();
                $table->timestamps();

                $table->index(['zone_id', 'mode', 'is_active'], 'idx_zone_process_calibration_zone_mode_active');
                $table->index(['zone_id', 'valid_from'], 'idx_zone_process_calibration_zone_valid_from');
            });
        }

        Schema::table('pid_state', function (Blueprint $table) {
            if (! Schema::hasColumn('pid_state', 'hold_until')) {
                $table->timestampTz('hold_until')->nullable()->after('last_dose_at');
            }
            if (! Schema::hasColumn('pid_state', 'last_measurement_at')) {
                $table->timestampTz('last_measurement_at')->nullable()->after('hold_until');
            }
            if (! Schema::hasColumn('pid_state', 'last_measured_value')) {
                $table->float('last_measured_value')->nullable()->after('last_measurement_at');
            }
            if (! Schema::hasColumn('pid_state', 'feedforward_bias')) {
                $table->float('feedforward_bias')->default(0.0)->after('last_measured_value');
            }
            if (! Schema::hasColumn('pid_state', 'no_effect_count')) {
                $table->unsignedInteger('no_effect_count')->default(0)->after('feedforward_bias');
            }
            if (! Schema::hasColumn('pid_state', 'last_correction_kind')) {
                $table->string('last_correction_kind', 32)->nullable()->after('no_effect_count');
            }
        });
    }

    public function down(): void
    {
        Schema::table('pid_state', function (Blueprint $table) {
            $columns = array_filter([
                Schema::hasColumn('pid_state', 'hold_until') ? 'hold_until' : null,
                Schema::hasColumn('pid_state', 'last_measurement_at') ? 'last_measurement_at' : null,
                Schema::hasColumn('pid_state', 'last_measured_value') ? 'last_measured_value' : null,
                Schema::hasColumn('pid_state', 'feedforward_bias') ? 'feedforward_bias' : null,
                Schema::hasColumn('pid_state', 'no_effect_count') ? 'no_effect_count' : null,
                Schema::hasColumn('pid_state', 'last_correction_kind') ? 'last_correction_kind' : null,
            ]);

            if ($columns !== []) {
                $table->dropColumn($columns);
            }
        });

        Schema::dropIfExists('zone_process_calibrations');

        Schema::table('pump_calibrations', function (Blueprint $table) {
            if (Schema::hasColumn('pump_calibrations', 'mode')) {
                $table->dropIndex('idx_pump_calibration_node_mode_active');
            }

            $columns = array_filter([
                Schema::hasColumn('pump_calibrations', 'mode') ? 'mode' : null,
                Schema::hasColumn('pump_calibrations', 'min_effective_ml') ? 'min_effective_ml' : null,
                Schema::hasColumn('pump_calibrations', 'transport_delay_sec') ? 'transport_delay_sec' : null,
                Schema::hasColumn('pump_calibrations', 'deadtime_sec') ? 'deadtime_sec' : null,
                Schema::hasColumn('pump_calibrations', 'curve_points') ? 'curve_points' : null,
            ]);

            if ($columns !== []) {
                $table->dropColumn($columns);
            }
        });
    }
};
