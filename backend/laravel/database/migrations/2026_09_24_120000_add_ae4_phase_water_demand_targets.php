<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        foreach (['recipe_revision_phases', 'grow_cycle_phases'] as $tableName) {
            Schema::table($tableName, function (Blueprint $table): void {
                $table->decimal('soil_moisture_min', 5, 2)->nullable()->after('irrigation_duration_sec');
                $table->decimal('soil_moisture_max', 5, 2)->nullable()->after('soil_moisture_min');
                $table->decimal('vpd_min', 5, 3)->nullable()->after('soil_moisture_max');
                $table->decimal('vpd_max', 5, 3)->nullable()->after('vpd_min');
                $table->decimal('light_integral_per_shot', 12, 3)->nullable()->after('vpd_max');
            });
        }
    }

    public function down(): void
    {
        foreach (['recipe_revision_phases', 'grow_cycle_phases'] as $tableName) {
            Schema::table($tableName, function (Blueprint $table): void {
                $table->dropColumn([
                    'soil_moisture_min',
                    'soil_moisture_max',
                    'vpd_min',
                    'vpd_max',
                    'light_integral_per_shot',
                ]);
            });
        }
    }
};
