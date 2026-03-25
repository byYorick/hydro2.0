<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        DB::table('zone_pid_configs')
            ->orderBy('id')
            ->chunkById(100, function ($rows): void {
                foreach ($rows as $row) {
                    $config = json_decode((string) $row->config, true);
                    if (! is_array($config)) {
                        continue;
                    }

                    $normalized = $this->normalizeLegacyConfigForMigration(
                        $config,
                        (string) $row->type
                    );

                    DB::table('zone_pid_configs')
                        ->where('id', $row->id)
                        ->update([
                            'config' => json_encode(
                                $this->sanitizeConfig($normalized),
                                JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES
                            ),
                            'updated_at' => now(),
                        ]);
                }
            });
    }

    public function down(): void
    {
        // Breaking cleanup: legacy flat PID contract is intentionally not restored.
    }

    private function normalizeLegacyConfigForMigration(
        array $config,
        string $type,
    ): array {
        if (isset($config['controller']) && is_array($config['controller'])) {
            return $config;
        }

        $controller = $this->defaultLegacyController($type);
        $closeCoeffs = is_array(data_get($config, 'zone_coeffs.close')) ? data_get($config, 'zone_coeffs.close') : [];

        $controller['kp'] = (float) ($config['kp'] ?? $closeCoeffs['kp'] ?? $controller['kp']);
        $controller['ki'] = (float) ($config['ki'] ?? $closeCoeffs['ki'] ?? $controller['ki']);
        $controller['kd'] = (float) ($config['kd'] ?? $closeCoeffs['kd'] ?? $controller['kd']);
        $controller['deadband'] = (float) ($config['dead_zone'] ?? $controller['deadband']);
        $controller['max_dose_ml'] = (float) ($config['max_output'] ?? $controller['max_dose_ml']);
        $controller['max_integral'] = (float) ($config['max_integral'] ?? $controller['max_integral']);

        $minIntervalMs = $config['min_interval_ms'] ?? null;
        if (is_numeric($minIntervalMs)) {
            $controller['min_interval_sec'] = max(1, (int) ceil(((float) $minIntervalMs) / 1000));
        }

        return [
            'controller' => $controller,
            'autotune_meta' => is_array($config['autotune_meta'] ?? null) ? $config['autotune_meta'] : null,
        ];
    }

    private function sanitizeConfig(array $config): array
    {
        return array_is_list($config) ? [] : $config;
    }

    /**
     * @return array<string, float|int>
     */
    private function defaultLegacyController(string $type): array
    {
        return $type === 'ph'
            ? [
                'kp' => 5.0,
                'ki' => 0.05,
                'kd' => 0.0,
                'deadband' => 0.05,
                'min_interval_sec' => 90,
                'max_dose_ml' => 20.0,
                'max_integral' => 20.0,
                'derivative_filter_alpha' => 0.35,
            ]
            : [
                'kp' => 30.0,
                'ki' => 0.3,
                'kd' => 0.0,
                'deadband' => 0.1,
                'min_interval_sec' => 120,
                'max_dose_ml' => 50.0,
                'max_integral' => 100.0,
                'derivative_filter_alpha' => 0.35,
            ];
    }
};
