<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('recipe_revision_phases', function (Blueprint $table) {
            $table->string('nutrient_program_code', 64)->nullable()->after('ec_max');
            $table->decimal('nutrient_npk_ratio_pct', 5, 2)->nullable()->after('nutrient_program_code');
            $table->decimal('nutrient_calcium_ratio_pct', 5, 2)->nullable()->after('nutrient_npk_ratio_pct');
            $table->decimal('nutrient_micro_ratio_pct', 5, 2)->nullable()->after('nutrient_calcium_ratio_pct');
            $table->decimal('nutrient_npk_dose_ml_l', 8, 3)->nullable()->after('nutrient_micro_ratio_pct');
            $table->decimal('nutrient_calcium_dose_ml_l', 8, 3)->nullable()->after('nutrient_npk_dose_ml_l');
            $table->decimal('nutrient_micro_dose_ml_l', 8, 3)->nullable()->after('nutrient_calcium_dose_ml_l');

            $table->index('nutrient_program_code', 'recipe_revision_phases_nutrient_program_idx');
        });
    }

    public function down(): void
    {
        Schema::table('recipe_revision_phases', function (Blueprint $table) {
            $table->dropIndex('recipe_revision_phases_nutrient_program_idx');
            $table->dropColumn([
                'nutrient_program_code',
                'nutrient_npk_ratio_pct',
                'nutrient_calcium_ratio_pct',
                'nutrient_micro_ratio_pct',
                'nutrient_npk_dose_ml_l',
                'nutrient_calcium_dose_ml_l',
                'nutrient_micro_dose_ml_l',
            ]);
        });
    }
};
