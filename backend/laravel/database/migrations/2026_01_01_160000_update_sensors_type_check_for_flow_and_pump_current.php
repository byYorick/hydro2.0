<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        if (!Schema::hasTable('sensors')) {
            return;
        }

        DB::statement('ALTER TABLE sensors DROP CONSTRAINT IF EXISTS sensors_type_check');

        DB::statement("
            ALTER TABLE sensors
            ADD CONSTRAINT sensors_type_check
            CHECK (type IN (
                'TEMPERATURE',
                'HUMIDITY',
                'CO2',
                'PH',
                'EC',
                'WATER_LEVEL',
                'FLOW_RATE',
                'PUMP_CURRENT',
                'WIND_SPEED',
                'WIND_DIRECTION',
                'PRESSURE',
                'LIGHT_INTENSITY',
                'SOIL_MOISTURE',
                'OTHER'
            ))
        ");
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        if (!Schema::hasTable('sensors')) {
            return;
        }

        DB::statement('ALTER TABLE sensors DROP CONSTRAINT IF EXISTS sensors_type_check');

        DB::statement("
            ALTER TABLE sensors
            ADD CONSTRAINT sensors_type_check
            CHECK (type IN (
                'TEMPERATURE',
                'HUMIDITY',
                'CO2',
                'PH',
                'EC',
                'WATER_LEVEL',
                'WIND_SPEED',
                'WIND_DIRECTION',
                'PRESSURE',
                'LIGHT_INTENSITY',
                'SOIL_MOISTURE',
                'OTHER'
            ))
        ");
    }
};
