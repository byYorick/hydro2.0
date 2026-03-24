<?php

use App\Services\ZonePidConfigurationService;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        $service = app(ZonePidConfigurationService::class);

        DB::table('zone_pid_configs')
            ->orderBy('id')
            ->chunkById(100, function ($rows) use ($service): void {
                foreach ($rows as $row) {
                    $config = json_decode((string) $row->config, true);
                    if (! is_array($config)) {
                        continue;
                    }

                    $normalized = $this->normalizeLegacyConfigForMigration(
                        $config,
                        (string) $row->type,
                        $service
                    );

                    DB::table('zone_pid_configs')
                        ->where('id', $row->id)
                        ->update([
                            'config' => json_encode(
                                $service->sanitizeConfig($normalized, (string) $row->type),
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
        ZonePidConfigurationService $service
    ): array {
        if (isset($config['controller']) && is_array($config['controller'])) {
            return $config;
        }

        $defaults = $service->getDefaultConfig($type);
        $controller = is_array($defaults['controller'] ?? null) ? $defaults['controller'] : [];
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
};
