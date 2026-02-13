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
        if (!Schema::hasTable('nodes')) {
            return;
        }

        DB::statement("
            UPDATE nodes
            SET type = CASE
                WHEN type IS NULL THEN 'unknown'
                WHEN LOWER(TRIM(type)) = '' THEN 'unknown'
                WHEN LOWER(TRIM(type)) IN ('ph', 'ph_node') THEN 'ph'
                WHEN LOWER(TRIM(type)) IN ('ec', 'ec_node') THEN 'ec'
                WHEN LOWER(TRIM(type)) IN ('climate', 'climate_node', 'climate_control', 'ventilation') THEN 'climate'
                WHEN LOWER(TRIM(type)) IN ('irrig', 'pump', 'pump_node', 'irrigation', 'irrigation_node') THEN 'irrig'
                WHEN LOWER(TRIM(type)) IN ('light', 'lighting', 'lighting_node', 'light_node') THEN 'light'
                WHEN LOWER(TRIM(type)) IN ('relay', 'relay_node') THEN 'relay'
                WHEN LOWER(TRIM(type)) IN ('water_sensor', 'water_sensor_node', 'water') THEN 'water_sensor'
                WHEN LOWER(TRIM(type)) IN ('recirculation', 'recirc', 'recirculation_pump') THEN 'recirculation'
                WHEN LOWER(TRIM(type)) = 'unknown' THEN 'unknown'
                ELSE 'unknown'
            END
        ");

        DB::statement('ALTER TABLE nodes DROP CONSTRAINT IF EXISTS nodes_type_canonical_check');

        DB::statement("
            ALTER TABLE nodes
            ADD CONSTRAINT nodes_type_canonical_check
            CHECK (
                type IN (
                    'ph',
                    'ec',
                    'climate',
                    'irrig',
                    'light',
                    'relay',
                    'water_sensor',
                    'recirculation',
                    'unknown'
                )
            )
        ");

        DB::statement("ALTER TABLE nodes ALTER COLUMN type SET DEFAULT 'unknown'");
        DB::statement("ALTER TABLE nodes ALTER COLUMN type SET NOT NULL");
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        if (!Schema::hasTable('nodes')) {
            return;
        }

        DB::statement('ALTER TABLE nodes DROP CONSTRAINT IF EXISTS nodes_type_canonical_check');
        DB::statement('ALTER TABLE nodes ALTER COLUMN type DROP NOT NULL');
        DB::statement('ALTER TABLE nodes ALTER COLUMN type DROP DEFAULT');
    }
};
