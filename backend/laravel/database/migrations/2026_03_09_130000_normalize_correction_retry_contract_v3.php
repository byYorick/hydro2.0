<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        $this->normalizeTable(
            table: 'zone_correction_presets',
            idColumn: 'id',
            columns: ['config']
        );

        $this->normalizeTable(
            table: 'zone_correction_configs',
            idColumn: 'id',
            columns: ['base_config', 'phase_overrides', 'resolved_config']
        );

        $this->normalizeTable(
            table: 'zone_correction_config_versions',
            idColumn: 'id',
            columns: ['base_config', 'phase_overrides', 'resolved_config']
        );
    }

    public function down(): void
    {
        // Irreversible normalization: v3 removes legacy retry.max_correction_attempts.
    }

    private function normalizeTable(string $table, string $idColumn, array $columns): void
    {
        $rows = DB::table($table)->select(array_merge([$idColumn], $columns))->get();
        foreach ($rows as $row) {
            $updates = [];
            foreach ($columns as $column) {
                $value = $row->{$column};
                $decoded = is_array($value) ? $value : json_decode((string) $value, true);
                if (! is_array($decoded)) {
                    continue;
                }
                $normalized = $this->normalizeConfigNode($decoded);
                if ($normalized !== $decoded) {
                    $updates[$column] = json_encode($normalized, JSON_THROW_ON_ERROR);
                }
            }
            if ($updates !== []) {
                $updates['updated_at'] = now();
                DB::table($table)->where($idColumn, $row->{$idColumn})->update($updates);
            }
        }
    }

    private function normalizeConfigNode(array $node): array
    {
        if (isset($node['base']) && is_array($node['base'])) {
            $node['base'] = $this->normalizeConfigNode($node['base']);
        }
        if (isset($node['phases']) && is_array($node['phases'])) {
            foreach ($node['phases'] as $phase => $config) {
                if (is_array($config)) {
                    $node['phases'][$phase] = $this->normalizeConfigNode($config);
                }
            }
        }
        if (isset($node['retry']) && is_array($node['retry'])) {
            $retry = $node['retry'];
            $legacy = $retry['max_correction_attempts'] ?? null;
            if (! array_key_exists('max_ec_correction_attempts', $retry) && $legacy !== null) {
                $retry['max_ec_correction_attempts'] = $legacy;
            }
            if (! array_key_exists('max_ph_correction_attempts', $retry) && $legacy !== null) {
                $retry['max_ph_correction_attempts'] = $legacy;
            }
            unset($retry['max_correction_attempts']);
            $node['retry'] = $retry;
        }
        if (isset($node['adaptive_mix_wait']) && is_array($node['adaptive_mix_wait'])) {
            if (! array_key_exists('enabled', $node['adaptive_mix_wait'])) {
                $node['adaptive_mix_wait']['enabled'] = true;
            }
            if (! array_key_exists('reference_volume_l', $node['adaptive_mix_wait'])) {
                $node['adaptive_mix_wait']['reference_volume_l'] = 100.0;
            }
        }

        return $node;
    }
};
