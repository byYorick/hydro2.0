<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * AE3 min-check задержки в пресетах: без блока fail_safe_guards в JSON применение пресета
     * и конвертер могли уводить нули в logic_profile.
     *
     * @var array<string, int|bool>
     */
    private const DEFAULT_FAIL_SAFE_GUARDS = [
        'clean_fill_min_check_delay_ms' => 5000,
        'solution_fill_clean_min_check_delay_ms' => 5000,
        'solution_fill_solution_min_check_delay_ms' => 15000,
        'recirculation_stop_on_solution_min' => true,
        'irrigation_stop_on_solution_min' => true,
        'estop_debounce_ms' => 80,
    ];

    public function up(): void
    {
        foreach (DB::table('zone_automation_presets')->cursor() as $row) {
            $config = json_decode($row->config, true);
            if (! is_array($config)) {
                continue;
            }
            $startup = $config['startup'] ?? [];
            if (! is_array($startup)) {
                $startup = [];
            }
            $existing = $startup['fail_safe_guards'] ?? null;
            $startup['fail_safe_guards'] = is_array($existing)
                ? array_merge(self::DEFAULT_FAIL_SAFE_GUARDS, $existing)
                : self::DEFAULT_FAIL_SAFE_GUARDS;
            $config['startup'] = $startup;

            DB::table('zone_automation_presets')->where('id', $row->id)->update([
                'config' => json_encode($config, JSON_THROW_ON_ERROR),
                'updated_at' => now(),
            ]);
        }
    }

    public function down(): void
    {
        foreach (DB::table('zone_automation_presets')->cursor() as $row) {
            $config = json_decode($row->config, true);
            if (! is_array($config) || ! isset($config['startup']['fail_safe_guards'])) {
                continue;
            }
            unset($config['startup']['fail_safe_guards']);
            if ($config['startup'] === []) {
                unset($config['startup']);
            }

            DB::table('zone_automation_presets')->where('id', $row->id)->update([
                'config' => json_encode($config, JSON_THROW_ON_ERROR),
                'updated_at' => now(),
            ]);
        }
    }
};
