<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        $runtimeDefaults = [
            'required_node_type' => 'irrig',
            'clean_fill_timeout_sec' => 1200,
            'solution_fill_timeout_sec' => 1800,
            'clean_fill_retry_cycles' => 1,
            'level_switch_on_threshold' => 0.5,
            'clean_max_sensor_label' => 'level_clean_max',
            'clean_min_sensor_label' => 'level_clean_min',
            'solution_max_sensor_label' => 'level_solution_max',
            'solution_min_sensor_label' => 'level_solution_min',
        ];

        DB::table('zone_correction_presets')
            ->orderBy('id')
            ->each(function (object $row) use ($runtimeDefaults): void {
                $config = $this->toArray($row->config);
                DB::table('zone_correction_presets')
                    ->where('id', $row->id)
                    ->update([
                        'config' => $this->normalizePresetConfig($config, $runtimeDefaults),
                        'updated_at' => now(),
                    ]);
            });

        DB::table('zone_correction_configs')
            ->orderBy('id')
            ->each(function (object $row) use ($runtimeDefaults): void {
                $resolved = $this->toArray($row->resolved_config);
                DB::table('zone_correction_configs')
                    ->where('id', $row->id)
                    ->update([
                        'resolved_config' => $this->normalizeResolvedConfig($resolved, $runtimeDefaults),
                        'updated_at' => now(),
                    ]);
            });

        DB::table('zone_correction_config_versions')
            ->orderBy('id')
            ->each(function (object $row) use ($runtimeDefaults): void {
                $resolved = $this->toArray($row->resolved_config);
                DB::table('zone_correction_config_versions')
                    ->where('id', $row->id)
                    ->update([
                        'resolved_config' => $this->normalizeResolvedConfig($resolved, $runtimeDefaults),
                    ]);
            });
    }

    public function down(): void
    {
    }

    private function normalizePresetConfig(array $config, array $runtimeDefaults): array
    {
        if (isset($config['base']) && is_array($config['base'])) {
            $config['base'] = $this->mergeRuntime($config['base'], $runtimeDefaults);
            $phases = is_array($config['phases'] ?? null) ? $config['phases'] : [];
            foreach (['solution_fill', 'tank_recirc', 'irrigation'] as $phase) {
                $phaseConfig = is_array($phases[$phase] ?? null) ? $phases[$phase] : [];
                $phases[$phase] = $this->mergeRuntime($phaseConfig, $runtimeDefaults);
            }
            $config['phases'] = $phases;

            return $config;
        }

        return $this->mergeRuntime($config, $runtimeDefaults);
    }

    private function normalizeResolvedConfig(array $resolved, array $runtimeDefaults): array
    {
        $base = is_array($resolved['base'] ?? null) ? $resolved['base'] : [];
        $resolved['base'] = $this->mergeRuntime($base, $runtimeDefaults);

        $phases = is_array($resolved['phases'] ?? null) ? $resolved['phases'] : [];
        foreach (['solution_fill', 'tank_recirc', 'irrigation'] as $phase) {
            $phaseConfig = is_array($phases[$phase] ?? null) ? $phases[$phase] : [];
            $phases[$phase] = $this->mergeRuntime($phaseConfig, $runtimeDefaults);
        }
        $resolved['phases'] = $phases;

        return $resolved;
    }

    private function mergeRuntime(array $config, array $runtimeDefaults): array
    {
        $runtime = is_array($config['runtime'] ?? null) ? $config['runtime'] : [];
        $config['runtime'] = array_replace($runtimeDefaults, $runtime);

        return $config;
    }

    private function toArray(mixed $value): array
    {
        if (is_array($value)) {
            return $value;
        }
        if (is_string($value) && $value !== '') {
            $decoded = json_decode($value, true);
            if (is_array($decoded)) {
                return $decoded;
            }
        }

        return [];
    }
};
