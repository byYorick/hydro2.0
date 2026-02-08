<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        DB::transaction(function (): void {
            $roleMap = [
                'ph_acid_pump' => ['ph_acid_pump', 'pump_acid', 'acid_pump', 'ph_acid', 'acid'],
                'ph_base_pump' => ['ph_base_pump', 'pump_base', 'base_pump', 'ph_base', 'base'],
                'ec_npk_pump' => ['ec_npk_pump', 'pump_nutrient_a', 'pump_a', 'nutrient_a', 'npk'],
                'ec_calcium_pump' => ['ec_calcium_pump', 'pump_nutrient_b', 'pump_b', 'nutrient_b', 'calcium', 'calmag'],
                'ec_magnesium_pump' => ['ec_magnesium_pump', 'pump_nutrient_c', 'pump_c', 'nutrient_c', 'magnesium', 'mg', 'mgso4'],
                'ec_micro_pump' => ['ec_micro_pump', 'pump_nutrient_d', 'pump_d', 'nutrient_d', 'micro'],
            ];

            foreach ($roleMap as $canonicalRole => $legacyRoles) {
                DB::table('channel_bindings')
                    ->whereIn('role', $legacyRoles)
                    ->update([
                        'role' => $canonicalRole,
                        'updated_at' => now(),
                    ]);
            }

            $channelComponentMap = [
                'pump_acid' => 'ph_down',
                'pump_base' => 'ph_up',
                'pump_a' => 'npk',
                'pump_b' => 'calcium',
                'pump_c' => 'magnesium',
                'pump_d' => 'micro',
                'pump_nutrient_a' => 'npk',
                'pump_nutrient_b' => 'calcium',
                'pump_nutrient_c' => 'magnesium',
                'pump_nutrient_d' => 'micro',
            ];

            foreach ($channelComponentMap as $channel => $component) {
                DB::update(
                    "
                    UPDATE node_channels
                    SET config = jsonb_set(
                        COALESCE(config, '{}'::jsonb),
                        '{pump_calibration,component}',
                        to_jsonb(?::text),
                        true
                    ),
                    updated_at = NOW()
                    WHERE channel = ?
                    ",
                    [$component, $channel]
                );
            }
        });
    }

    public function down(): void
    {
        // Revert невозможен без потери смысла нормализации role/component.
    }
};
