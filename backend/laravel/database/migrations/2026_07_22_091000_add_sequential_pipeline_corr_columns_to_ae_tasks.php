<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table): void {
            if (! Schema::hasColumn('ae_tasks', 'corr_pipeline_phase')) {
                $table->string('corr_pipeline_phase', 64)->nullable()->after('corr_step');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_active_component')) {
                $table->string('corr_active_component', 64)->nullable()->after('corr_pipeline_phase');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_water_ec')) {
                $table->decimal('corr_water_ec', 10, 4)->nullable()->after('corr_active_component');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_water_ph')) {
                $table->decimal('corr_water_ph', 10, 4)->nullable()->after('corr_water_ec');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_nutrient_budget')) {
                $table->decimal('corr_nutrient_budget', 10, 4)->nullable()->after('corr_water_ph');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_component_targets_json')) {
                $table->jsonb('corr_component_targets_json')->nullable()->after('corr_nutrient_budget');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_dilute_attempts')) {
                $table->unsignedInteger('corr_dilute_attempts')->nullable()->after('corr_component_targets_json');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_ec_pid_frozen')) {
                $table->boolean('corr_ec_pid_frozen')->nullable()->after('corr_dilute_attempts');
            }
            if (! Schema::hasColumn('ae_tasks', 'corr_baseline_id')) {
                $table->unsignedBigInteger('corr_baseline_id')->nullable()->after('corr_ec_pid_frozen');
            }
        });

        if (Schema::hasTable('zone_prepare_baselines') && Schema::hasColumn('ae_tasks', 'corr_baseline_id')) {
            Schema::table('ae_tasks', function (Blueprint $table): void {
                $table->foreign('corr_baseline_id')
                    ->references('id')
                    ->on('zone_prepare_baselines')
                    ->nullOnDelete();
            });
        }
    }

    public function down(): void
    {
        if (! Schema::hasTable('ae_tasks')) {
            return;
        }

        Schema::table('ae_tasks', function (Blueprint $table): void {
            if (Schema::hasColumn('ae_tasks', 'corr_baseline_id')) {
                $table->dropForeign(['corr_baseline_id']);
            }
        });

        Schema::table('ae_tasks', function (Blueprint $table): void {
            $drops = array_values(array_filter([
                Schema::hasColumn('ae_tasks', 'corr_baseline_id') ? 'corr_baseline_id' : null,
                Schema::hasColumn('ae_tasks', 'corr_ec_pid_frozen') ? 'corr_ec_pid_frozen' : null,
                Schema::hasColumn('ae_tasks', 'corr_dilute_attempts') ? 'corr_dilute_attempts' : null,
                Schema::hasColumn('ae_tasks', 'corr_component_targets_json') ? 'corr_component_targets_json' : null,
                Schema::hasColumn('ae_tasks', 'corr_nutrient_budget') ? 'corr_nutrient_budget' : null,
                Schema::hasColumn('ae_tasks', 'corr_water_ph') ? 'corr_water_ph' : null,
                Schema::hasColumn('ae_tasks', 'corr_water_ec') ? 'corr_water_ec' : null,
                Schema::hasColumn('ae_tasks', 'corr_active_component') ? 'corr_active_component' : null,
                Schema::hasColumn('ae_tasks', 'corr_pipeline_phase') ? 'corr_pipeline_phase' : null,
            ]));

            if ($drops !== []) {
                $table->dropColumn($drops);
            }
        });
    }
};
