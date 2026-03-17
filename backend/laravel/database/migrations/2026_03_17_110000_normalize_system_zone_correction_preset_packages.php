<?php

use App\Services\ZoneCorrectionConfigCatalog;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    private const PHASES = ['solution_fill', 'tank_recirc', 'irrigation'];

    public function up(): void
    {
        $this->rewriteSystemPresetPackages(
            fn (array $base, array $phases): array => $this->normalizePhases($base, $phases),
            compressBase: false,
        );
    }

    public function down(): void
    {
        $this->rewriteSystemPresetPackages(
            fn (array $base, array $phases): array => $this->compressPhases($base, $phases),
            compressBase: true,
        );
    }

    private function rewriteSystemPresetPackages(callable $transform, bool $compressBase): void
    {
        $defaults = ZoneCorrectionConfigCatalog::defaults();

        DB::table('zone_correction_presets')
            ->where('scope', 'system')
            ->orderBy('id')
            ->get(['id', 'config'])
            ->each(function (object $preset) use ($compressBase, $defaults, $transform): void {
                $config = $this->decodeConfig($preset->config ?? null);
                $base = $config['base'] ?? null;
                $phases = $config['phases'] ?? null;
                if (! is_array($base) || array_is_list($base) || ! is_array($phases) || array_is_list($phases)) {
                    return;
                }

                $normalizedBase = $this->mergeRecursive($defaults, $base);
                DB::table('zone_correction_presets')
                    ->where('id', $preset->id)
                    ->update([
                        'config' => json_encode([
                            'base' => $compressBase
                                ? $this->diffRecursive($defaults, $base)
                                : $normalizedBase,
                            'phases' => $transform($normalizedBase, $phases),
                        ], JSON_THROW_ON_ERROR),
                        'updated_at' => now(),
                    ]);
            });
    }

    private function normalizePhases(array $base, array $phases): array
    {
        $normalized = [];
        foreach (self::PHASES as $phase) {
            $override = $phases[$phase] ?? [];
            $normalized[$phase] = $this->mergeRecursive(
                $base,
                is_array($override) && ! array_is_list($override) ? $override : []
            );
        }

        return $normalized;
    }

    private function compressPhases(array $base, array $phases): array
    {
        $compressed = [];
        foreach (self::PHASES as $phase) {
            $phaseConfig = $phases[$phase] ?? [];
            $compressed[$phase] = $this->diffRecursive(
                $base,
                is_array($phaseConfig) && ! array_is_list($phaseConfig) ? $phaseConfig : []
            );
        }

        return $compressed;
    }

    private function mergeRecursive(array $base, array $override): array
    {
        foreach ($override as $key => $value) {
            if (
                $value === []
                && isset($base[$key])
                && is_array($base[$key])
                && ! array_is_list($base[$key])
            ) {
                continue;
            }

            if (
                is_array($value)
                && isset($base[$key])
                && is_array($base[$key])
                && ! array_is_list($value)
                && ! array_is_list($base[$key])
            ) {
                $base[$key] = $this->mergeRecursive($base[$key], $value);
                continue;
            }

            $base[$key] = $value;
        }

        return $base;
    }

    private function diffRecursive(array $base, array $target): array
    {
        $diff = [];
        foreach ($target as $key => $value) {
            if (! array_key_exists($key, $base)) {
                $diff[$key] = $value;
                continue;
            }

            $baseValue = $base[$key];
            if (
                is_array($value)
                && is_array($baseValue)
                && ! array_is_list($value)
                && ! array_is_list($baseValue)
            ) {
                $nested = $this->diffRecursive($baseValue, $value);
                if ($nested !== []) {
                    $diff[$key] = $nested;
                }
                continue;
            }

            if ($value !== $baseValue) {
                $diff[$key] = $value;
            }
        }

        return $diff;
    }

    private function decodeConfig(mixed $raw): array
    {
        if (is_array($raw)) {
            return $raw;
        }
        if (! is_string($raw) || trim($raw) === '') {
            return [];
        }

        $decoded = json_decode($raw, true);

        return is_array($decoded) ? $decoded : [];
    }
};
