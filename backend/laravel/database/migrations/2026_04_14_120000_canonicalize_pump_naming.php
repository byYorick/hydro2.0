<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Унификация имён насосов по всей системе.
 *
 * После миграции `channel_bindings.role` для насосов равен канонич-
 * ному имени физического канала из NodeConfig (см.
 * doc_ai/01_SYSTEM/PUMP_NAMING_UNIFICATION_PLAN.md).
 *
 * Rewrite table:
 *   ph_acid_pump      -> pump_acid
 *   ph_base_pump      -> pump_base
 *   ec_npk_pump       -> pump_a
 *   ec_calcium_pump   -> pump_b
 *   ec_magnesium_pump -> pump_c
 *   ec_micro_pump     -> pump_d
 *   main_pump         -> pump_main
 *   pump_irrigation   -> pump_main
 *   dose_ph_down      -> pump_acid
 *   dose_ph_up        -> pump_base
 *   dose_ec_a         -> pump_a
 *   dose_ec_b         -> pump_b
 *   dose_ec_c         -> pump_c
 *   dose_ec_d         -> pump_d
 */
return new class extends Migration
{
    private const ROLE_MAP = [
        'ph_acid_pump' => 'pump_acid',
        'ph_base_pump' => 'pump_base',
        'ec_npk_pump' => 'pump_a',
        'ec_calcium_pump' => 'pump_b',
        'ec_magnesium_pump' => 'pump_c',
        'ec_micro_pump' => 'pump_d',
        'main_pump' => 'pump_main',
        'pump_irrigation' => 'pump_main',
        'irrigation_pump' => 'pump_main',
    ];

    private const DOSE_CHANNEL_MAP = [
        'dose_ph_down' => 'pump_acid',
        'dose_ph_up' => 'pump_base',
        'dose_ec_a' => 'pump_a',
        'dose_ec_b' => 'pump_b',
        'dose_ec_c' => 'pump_c',
        'dose_ec_d' => 'pump_d',
        'ph_acid_pump' => 'pump_acid',
        'ph_base_pump' => 'pump_base',
        'ec_npk_pump' => 'pump_a',
        'ec_calcium_pump' => 'pump_b',
        'ec_magnesium_pump' => 'pump_c',
        'ec_micro_pump' => 'pump_d',
    ];

    public function up(): void
    {
        DB::transaction(function (): void {
            foreach (self::ROLE_MAP as $legacy => $canonical) {
                DB::table('channel_bindings')
                    ->where('role', $legacy)
                    ->update([
                        'role' => $canonical,
                        'updated_at' => now(),
                    ]);
            }

            if (DB::getSchemaBuilder()->hasTable('zone_channel_bindings')) {
                foreach (self::ROLE_MAP as $legacy => $canonical) {
                    DB::table('zone_channel_bindings')
                        ->where('role', $legacy)
                        ->update([
                            'role' => $canonical,
                            'updated_at' => now(),
                        ]);
                }
            }

            $this->rewriteDoseChannels();

            $this->warnOnUnknownPumpRoles();
        });
    }

    public function down(): void
    {
        // Один из канонических идентификаторов отвечает сразу нескольким
        // legacy alias (pump_main <- main_pump|pump_irrigation), поэтому
        // обратная миграция невозможна без потери данных.
    }

    private function rewriteDoseChannels(): void
    {
        $this->rewriteInTable(
            'zone_correction_presets',
            'config',
            ['base', 'dosing'],
        );

        $this->rewriteInTable(
            'automation_config_documents',
            'payload',
            ['base_config', 'dosing'],
        );

        $this->rewriteInTable(
            'automation_config_versions',
            'payload',
            ['base_config', 'dosing'],
        );

        $this->rewriteInTable(
            'automation_config_presets',
            'config',
            ['base', 'dosing'],
        );

        $this->rewriteInTable(
            'automation_config_preset_versions',
            'config',
            ['base', 'dosing'],
        );
    }

    private function rewriteInTable(string $table, string $column, array $dosingPath): void
    {
        $schema = DB::getSchemaBuilder();
        if (! $schema->hasTable($table) || ! $schema->hasColumn($table, $column)) {
            return;
        }

        $rows = DB::table($table)
            ->select(['id', $column])
            ->get();

        foreach ($rows as $row) {
            $raw = $row->{$column};
            $config = is_string($raw) ? json_decode($raw, true) : (is_array($raw) ? $raw : null);
            if (! is_array($config)) {
                continue;
            }

            $dosing = $this->digPath($config, $dosingPath);
            if (! is_array($dosing)) {
                continue;
            }

            $changed = false;
            foreach (['dose_ec_channel', 'dose_ph_up_channel', 'dose_ph_down_channel'] as $key) {
                $value = $dosing[$key] ?? null;
                if (! is_string($value) || $value === '') {
                    continue;
                }
                $lower = strtolower(trim($value));
                if (isset(self::DOSE_CHANNEL_MAP[$lower]) && $dosing[$key] !== self::DOSE_CHANNEL_MAP[$lower]) {
                    $dosing[$key] = self::DOSE_CHANNEL_MAP[$lower];
                    $changed = true;
                }
            }

            if ($changed) {
                $this->setPath($config, $dosingPath, $dosing);
                DB::table($table)
                    ->where('id', $row->id)
                    ->update([
                        $column => json_encode($config, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                        'updated_at' => now(),
                    ]);
            }
        }
    }

    private function digPath(array $config, array $path): mixed
    {
        $cursor = $config;
        foreach ($path as $segment) {
            if (! is_array($cursor) || ! array_key_exists($segment, $cursor)) {
                return null;
            }
            $cursor = $cursor[$segment];
        }

        return $cursor;
    }

    private function setPath(array &$config, array $path, array $value): void
    {
        $cursor = &$config;
        foreach ($path as $segment) {
            if (! is_array($cursor[$segment] ?? null)) {
                $cursor[$segment] = [];
            }
            $cursor = &$cursor[$segment];
        }
        $cursor = $value;
    }

    private function warnOnUnknownPumpRoles(): void
    {
        $known = array_merge(
            array_values(self::ROLE_MAP),
            ['drain', 'drain_main', 'mister', 'fan', 'heater', 'light', 'vent',
                'ph_sensor', 'ec_sensor', 'temp_sensor', 'flow_sensor',
                'soil_moisture_sensor', 'water_level_sensor', 'co2_sensor',
                'humidity_sensor', 'lux_sensor', 'par_sensor']
        );

        $unknown = DB::table('channel_bindings')
            ->select('role')
            ->where('role', 'like', '%pump%')
            ->whereNotIn('role', $known)
            ->distinct()
            ->pluck('role')
            ->all();

        if (! empty($unknown)) {
            Log::warning('canonicalize_pump_naming: found unknown pump roles in channel_bindings', [
                'roles' => $unknown,
            ]);
        }
    }
};
