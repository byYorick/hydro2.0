<?php

namespace App\Services\CropDay;

/**
 * dli_mol = sum(ppfd * dt_sec) / 1_000_000.
 * dt_sec — до следующего образца и не больше дыры. Люкс не конвертируется.
 */
final class DliIntegral
{
    public const STALE_GAP_SEC = 600;

    /** @var list<string> */
    public const PPFD_UNITS = ['ppfd', 'umol_m2_s'];

    /**
     * @param  list<array{ts: int, value: float}>  $samples
     * @return array{dli_mol: float|null, status: string}
     */
    public static function integrate(array $samples, int $gapSec = self::STALE_GAP_SEC): array
    {
        $points = [];
        foreach ($samples as $sample) {
            if (! is_array($sample) || ! isset($sample['ts'], $sample['value'])) {
                continue;
            }
            if (! is_numeric($sample['ts']) || ! is_numeric($sample['value'])) {
                continue;
            }
            $points[] = ['ts' => (int) $sample['ts'], 'value' => (float) $sample['value']];
        }
        usort($points, static fn (array $left, array $right): int => $left['ts'] <=> $right['ts']);
        if ($points === []) {
            return ['dli_mol' => null, 'status' => 'sensor_unavailable'];
        }

        $gap = max(0, $gapSec);
        $total = 0.0;
        $last = count($points) - 1;
        for ($index = 0; $index < $last; $index++) {
            $dt = $points[$index + 1]['ts'] - $points[$index]['ts'];
            if ($dt > $gap) {
                return ['dli_mol' => null, 'status' => 'gap'];
            }
            if ($dt > 0) {
                $total += $points[$index]['value'] * $dt;
            }
        }

        return ['dli_mol' => round($total / 1_000_000, 6), 'status' => 'ok'];
    }

    public static function isPpfdUnit(?string $unit): bool
    {
        return in_array(trim((string) $unit), self::PPFD_UNITS, true);
    }

    public static function configuredUnit(mixed $columnUnit, mixed $config): string
    {
        $column = trim((string) ($columnUnit ?? ''));
        if (is_string($config) && $config !== '') {
            $decoded = json_decode($config, true);
            $config = is_array($decoded) ? $decoded : null;
        }
        $fromConfig = '';
        if (is_array($config) && array_key_exists('unit', $config) && is_scalar($config['unit'])) {
            $fromConfig = trim((string) $config['unit']);
        }
        if ($column !== '' && $fromConfig !== '' && $column !== $fromConfig) {
            return 'mixed';
        }

        return $column !== '' ? $column : $fromConfig;
    }
}
