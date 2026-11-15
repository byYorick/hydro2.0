<?php

namespace App\Services;

use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Уровни баков зоны из telemetry_last (sensors.type = WATER_LEVEL).
 * Семантика coarse % совпадает с дашбордом: solution max → 100, только min → 50.
 */
class ZoneTankLevelService
{
    /**
     * @return array{
     *     solution_percent: float|null,
     *     clean_percent: float|null,
     *     buffer_percent: float|null,
     *     solution_present: bool,
     *     clean_present: bool,
     *     buffer_present: bool,
     *     solution_offline: bool,
     *     clean_offline: bool,
     *     buffer_offline: bool,
     *     topology_count: int|null
     * }
     */
    public function forZone(int $zoneId): array
    {
        $empty = $this->emptyLevels();
        if ($zoneId <= 0 || ! Schema::hasTable('telemetry_last') || ! Schema::hasTable('sensors')) {
            return $empty;
        }

        try {
            $rows = DB::table('telemetry_last')
                ->join('sensors', 'telemetry_last.sensor_id', '=', 'sensors.id')
                ->where('sensors.zone_id', $zoneId)
                ->where('sensors.type', 'WATER_LEVEL')
                ->select([
                    DB::raw("COALESCE(NULLIF(sensors.specs->>'channel', ''), sensors.label) as channel"),
                    'telemetry_last.last_value as value',
                    'telemetry_last.updated_at',
                ])
                ->get();
        } catch (\Throwable) {
            return $empty;
        }

        if ($rows->isEmpty()) {
            return $empty;
        }

        $staleBefore = Carbon::now()->subMinutes(5);
        $buckets = [
            'clean' => [],
            'solution' => [],
            'buffer' => [],
            'clean_present' => false,
            'solution_present' => false,
            'buffer_present' => false,
        ];

        foreach ($rows as $row) {
            $channel = strtolower((string) ($row->channel ?? ''));
            $target = $this->tankOf($channel);
            if ($target === null) {
                continue;
            }
            $buckets[$target.'_present'] = true;
            $updatedAt = $row->updated_at ? Carbon::parse($row->updated_at) : null;
            $buckets[$target][] = [
                'value' => is_numeric($row->value) ? (float) $row->value : null,
                'stale' => $updatedAt === null || $updatedAt->lt($staleBefore),
                'channel' => $channel,
            ];
        }

        return [
            'solution_percent' => $this->aggregate($buckets['solution'], 'solution'),
            'clean_percent' => $this->aggregate($buckets['clean'], 'clean'),
            'buffer_percent' => $this->aggregate($buckets['buffer'], 'buffer'),
            'solution_present' => (bool) $buckets['solution_present'],
            'clean_present' => (bool) $buckets['clean_present'],
            'buffer_present' => (bool) $buckets['buffer_present'],
            'solution_offline' => $this->offline($buckets['solution']),
            'clean_offline' => $this->offline($buckets['clean']),
            'buffer_offline' => $this->offline($buckets['buffer']),
            'topology_count' => $this->topologyCount($buckets),
        ];
    }

    /**
     * @return array{solution_percent: null, clean_percent: null, buffer_percent: null, solution_present: false, clean_present: false, buffer_present: false, solution_offline: false, clean_offline: false, buffer_offline: false, topology_count: null}
     */
    private function emptyLevels(): array
    {
        return [
            'solution_percent' => null,
            'clean_percent' => null,
            'buffer_percent' => null,
            'solution_present' => false,
            'clean_present' => false,
            'buffer_present' => false,
            'solution_offline' => false,
            'clean_offline' => false,
            'buffer_offline' => false,
            'topology_count' => null,
        ];
    }

    private function tankOf(string $channel): ?string
    {
        if (str_contains($channel, 'clean') || str_contains($channel, 'fresh') || str_contains($channel, 'чист')) {
            return 'clean';
        }
        if (
            str_contains($channel, 'solution')
            || str_contains($channel, 'nutrient')
            || str_contains($channel, 'раств')
            || str_contains($channel, 'пит')
        ) {
            return 'solution';
        }
        if (
            str_contains($channel, 'buffer')
            || str_contains($channel, 'drain')
            || str_contains($channel, 'return')
            || str_contains($channel, 'буфер')
            || str_contains($channel, 'слив')
        ) {
            return 'buffer';
        }

        return null;
    }

    /**
     * @param  array<int, array{value: float|null, stale: bool, channel: string}>  $entries
     */
    private function aggregate(array $entries, string $tank): ?float
    {
        $fresh = array_values(array_filter(
            $entries,
            static fn (array $entry): bool => $entry['value'] !== null && ! $entry['stale']
        ));
        if ($fresh === []) {
            return null;
        }

        $maxSeen = false;
        $minSeen = false;
        $maxOn = false;
        $minOn = false;
        $continuous = [];

        foreach ($fresh as $entry) {
            $channel = $entry['channel'];
            $value = $entry['value'];
            $isMax = str_contains($channel, '_max') || str_ends_with($channel, 'max');
            $isMin = str_contains($channel, '_min') || str_ends_with($channel, 'min');
            if ($isMax) {
                $maxSeen = true;
                $maxOn = $maxOn || $value >= 0.5;
            } elseif ($isMin) {
                $minSeen = true;
                $minOn = $minOn || $value >= 0.5;
            } else {
                $continuous[] = $value;
            }
        }

        if ($maxSeen || $minSeen) {
            if ($tank === 'clean') {
                if ($maxSeen) {
                    return $maxOn ? 100.0 : 0.0;
                }

                return $minOn ? 50.0 : 0.0;
            }
            if ($maxOn) {
                return 100.0;
            }
            if ($minOn) {
                return 50.0;
            }

            return 0.0;
        }

        if ($continuous === []) {
            return null;
        }

        $allBinary = true;
        foreach ($continuous as $value) {
            if ($value !== 0.0 && $value !== 1.0) {
                $allBinary = false;
                break;
            }
        }
        if ($allBinary) {
            return max($continuous) >= 0.5 ? 100.0 : 0.0;
        }

        return round(max(0.0, min(100.0, array_sum($continuous) / count($continuous))), 1);
    }

    /**
     * @param  array<int, array{value: float|null, stale: bool, channel: string}>  $entries
     */
    private function offline(array $entries): bool
    {
        if ($entries === []) {
            return false;
        }
        foreach ($entries as $entry) {
            if (! $entry['stale'] && $entry['value'] !== null) {
                return false;
            }
        }

        return true;
    }

    /**
     * @param  array<string, mixed>  $buckets
     */
    private function topologyCount(array $buckets): ?int
    {
        if (! empty($buckets['buffer_present'])) {
            return 3;
        }
        $tanks = (int) ! empty($buckets['clean_present']) + (int) ! empty($buckets['solution_present']);
        if ($tanks === 0) {
            return null;
        }

        return $tanks;
    }
}
