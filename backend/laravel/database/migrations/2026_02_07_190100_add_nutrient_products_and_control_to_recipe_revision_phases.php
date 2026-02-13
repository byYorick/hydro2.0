<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('recipe_revision_phases', function (Blueprint $table) {
            $table->foreignId('nutrient_npk_product_id')
                ->nullable()
                ->after('nutrient_micro_dose_ml_l')
                ->constrained('nutrient_products')
                ->nullOnDelete();
            $table->foreignId('nutrient_calcium_product_id')
                ->nullable()
                ->after('nutrient_npk_product_id')
                ->constrained('nutrient_products')
                ->nullOnDelete();
            $table->foreignId('nutrient_micro_product_id')
                ->nullable()
                ->after('nutrient_calcium_product_id')
                ->constrained('nutrient_products')
                ->nullOnDelete();
            $table->integer('nutrient_dose_delay_sec')
                ->nullable()
                ->after('nutrient_micro_product_id');
            $table->decimal('nutrient_ec_stop_tolerance', 5, 3)
                ->nullable()
                ->after('nutrient_dose_delay_sec');
        });
    }

    public function down(): void
    {
        Schema::table('recipe_revision_phases', function (Blueprint $table) {
            $table->dropConstrainedForeignId('nutrient_npk_product_id');
            $table->dropConstrainedForeignId('nutrient_calcium_product_id');
            $table->dropConstrainedForeignId('nutrient_micro_product_id');
            $table->dropColumn([
                'nutrient_dose_delay_sec',
                'nutrient_ec_stop_tolerance',
            ]);
        });
    }
};
