<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Полная (рекурсивная) канонизация dosing-каналов в correction-конфигах.
 *
 * Миграция 2026_04_14_120000_canonicalize_pump_naming обновляла только
 * путь base_config.dosing / base.dosing и оставляла legacy-значения в
 * phase_overrides / resolved_config / вложенных фазах пресетов.
 * AE3 fail-closed: dose_ph_down_channel=dose_ph_down не резолвится в
 * actuator pump_acid → corr_planner_config_invalid.
 */
return new class extends Migration
{
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

    private const DOSE_CHANNEL_KEYS = [
        'dose_ec_channel',
        'dose_ph_up_channel',
        'dose_ph_down_channel',
    ];

    public function up(): void
    {
        DB::transaction(function (): void {
            $this->rewriteJsonColumn('automation_config_documents', 'payload', recomputeChecksum: true);
            $this->rewriteJsonColumn('automation_config_versions', 'payload', recomputeChecksum: false);
            $this->rewriteJsonColumn('automation_config_presets', 'payload', recomputeChecksum: false);
            $this->rewriteJsonColumn('automation_config_preset_versions', 'payload', recomputeChecksum: false);

            // Legacy UI tables (если ещё присутствуют в окружении).
            $this->rewriteJsonColumn('zone_correction_presets', 'config', recomputeChecksum: false);
            $this->rewriteJsonColumn('automation_config_presets', 'config', recomputeChecksum: false);
            $this->rewriteJsonColumn('automation_config_preset_versions', 'config', recomputeChecksum: false);
        });
    }

    public function down(): void
    {
        // Обратная миграция невозможна без потери данных: несколько legacy
        // alias сходятся в один канонический channel.
    }

    private function rewriteJsonColumn(string $table, string $column, bool $recomputeChecksum): void
    {
        if (! Schema::hasTable($table) || ! Schema::hasColumn($table, $column)) {
            return;
        }

        $select = ['id', $column];
        $hasChecksum = $recomputeChecksum && Schema::hasColumn($table, 'checksum');
        if ($hasChecksum) {
            $select[] = 'checksum';
        }

        $rows = DB::table($table)->select($select)->orderBy('id')->get();
        foreach ($rows as $row) {
            $raw = $row->{$column};
            $payload = is_string($raw) ? json_decode($raw, true) : (is_array($raw) ? $raw : null);
            if (! is_array($payload)) {
                continue;
            }

            $changed = $this->rewriteDoseChannelsRecursive($payload);
            if ($changed === 0) {
                continue;
            }

            $encoded = json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
            $update = [
                $column => $encoded,
                'updated_at' => now(),
            ];
            if ($hasChecksum) {
                $update['checksum'] = hash('sha1', $encoded ?: '{}');
            }

            DB::table($table)->where('id', $row->id)->update($update);
        }
    }

    /**
     * @param  array<mixed>  $node
     */
    private function rewriteDoseChannelsRecursive(array &$node): int
    {
        $changed = 0;
        foreach ($node as $key => &$value) {
            if (is_array($value)) {
                $changed += $this->rewriteDoseChannelsRecursive($value);

                continue;
            }

            if (! is_string($key) || ! in_array($key, self::DOSE_CHANNEL_KEYS, true) || ! is_string($value)) {
                continue;
            }

            $lower = strtolower(trim($value));
            if (isset(self::DOSE_CHANNEL_MAP[$lower]) && $value !== self::DOSE_CHANNEL_MAP[$lower]) {
                $value = self::DOSE_CHANNEL_MAP[$lower];
                $changed++;
            }
        }

        return $changed;
    }
};
