<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('recipe_revision_phases', function (Blueprint $table) {
            $table->string('nutrient_mode', 32)
                ->nullable()
                ->after('nutrient_program_code');
            $table->decimal('nutrient_magnesium_ratio_pct', 5, 2)
                ->nullable()
                ->after('nutrient_calcium_ratio_pct');
            $table->decimal('nutrient_magnesium_dose_ml_l', 8, 3)
                ->nullable()
                ->after('nutrient_calcium_dose_ml_l');
            $table->foreignId('nutrient_magnesium_product_id')
                ->nullable()
                ->after('nutrient_calcium_product_id')
                ->constrained('nutrient_products')
                ->nullOnDelete();
            $table->decimal('nutrient_solution_volume_l', 8, 2)
                ->nullable()
                ->after('nutrient_ec_stop_tolerance');
        });

        Schema::table('grow_cycle_phases', function (Blueprint $table) {
            $table->string('nutrient_mode', 32)
                ->nullable()
                ->after('nutrient_program_code');
            $table->decimal('nutrient_magnesium_ratio_pct', 5, 2)
                ->nullable()
                ->after('nutrient_calcium_ratio_pct');
            $table->decimal('nutrient_magnesium_dose_ml_l', 8, 3)
                ->nullable()
                ->after('nutrient_calcium_dose_ml_l');
            $table->foreignId('nutrient_magnesium_product_id')
                ->nullable()
                ->after('nutrient_calcium_product_id')
                ->constrained('nutrient_products')
                ->nullOnDelete();
            $table->decimal('nutrient_solution_volume_l', 8, 2)
                ->nullable()
                ->after('nutrient_ec_stop_tolerance');
        });
    }

    public function down(): void
    {
        Schema::table('grow_cycle_phases', function (Blueprint $table) {
            $table->dropConstrainedForeignId('nutrient_magnesium_product_id');
            $table->dropColumn([
                'nutrient_mode',
                'nutrient_magnesium_ratio_pct',
                'nutrient_magnesium_dose_ml_l',
                'nutrient_solution_volume_l',
            ]);
        });

        Schema::table('recipe_revision_phases', function (Blueprint $table) {
            $table->dropConstrainedForeignId('nutrient_magnesium_product_id');
            $table->dropColumn([
                'nutrient_mode',
                'nutrient_magnesium_ratio_pct',
                'nutrient_magnesium_dose_ml_l',
                'nutrient_solution_volume_l',
            ]);
        });
    }
};
