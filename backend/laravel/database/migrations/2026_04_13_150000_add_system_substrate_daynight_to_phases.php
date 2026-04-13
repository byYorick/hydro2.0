<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('recipe_revision_phases', function (Blueprint $table) {
            $table->string('irrigation_system_type', 32)->nullable()->after('irrigation_mode');
            $table->string('substrate_type', 64)->nullable()->after('irrigation_system_type');
            $table->boolean('day_night_enabled')->nullable()->after('substrate_type');
        });

        Schema::table('grow_cycle_phases', function (Blueprint $table) {
            $table->string('irrigation_system_type', 32)->nullable()->after('irrigation_mode');
            $table->string('substrate_type', 64)->nullable()->after('irrigation_system_type');
            $table->boolean('day_night_enabled')->nullable()->after('substrate_type');
        });
    }

    public function down(): void
    {
        Schema::table('recipe_revision_phases', function (Blueprint $table) {
            $table->dropColumn(['irrigation_system_type', 'substrate_type', 'day_night_enabled']);
        });

        Schema::table('grow_cycle_phases', function (Blueprint $table) {
            $table->dropColumn(['irrigation_system_type', 'substrate_type', 'day_night_enabled']);
        });
    }
};
