<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Погодные типы уже пишет history-logger и читает greenhouse climate.
     * Прежний CHECK их не содержал: миграция enum их не добавляла, колонка varchar.
     */
    public function up(): void
    {
        if (! Schema::hasTable('sensors')) {
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
                'SOIL_TEMP',
                'OUTSIDE_TEMP',
                'OUTSIDE_HUMIDITY',
                'OUTSIDE_PRESSURE',
                'OUTSIDE_LIGHT',
                'RAIN_DETECTED',
                'OTHER'
            ))
        ");
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        if (! Schema::hasTable('sensors')) {
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
};
