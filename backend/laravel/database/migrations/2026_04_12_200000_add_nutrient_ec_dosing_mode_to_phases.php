<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('recipe_revision_phases', function (Blueprint $table) {
            $table->string('nutrient_ec_dosing_mode', 32)->nullable()->after('nutrient_mode');
        });

        Schema::table('grow_cycle_phases', function (Blueprint $table) {
            $table->string('nutrient_ec_dosing_mode', 32)->nullable()->after('nutrient_mode');
        });
    }

    public function down(): void
    {
        Schema::table('recipe_revision_phases', function (Blueprint $table) {
            $table->dropColumn('nutrient_ec_dosing_mode');
        });

        Schema::table('grow_cycle_phases', function (Blueprint $table) {
            $table->dropColumn('nutrient_ec_dosing_mode');
        });
    }
};
