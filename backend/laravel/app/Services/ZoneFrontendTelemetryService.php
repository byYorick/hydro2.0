<?php

namespace App\Services;

use App\Models\Sensor;
use App\Models\TelemetryLast;

class ZoneFrontendTelemetryService
{
    private const DEFAULT_SNAPSHOT = [
        'ph' => null,
        'ec' => null,
        'temperature' => null,
        'humidity' => null,
        'co2' => null,
        'last_updated' => null,
    ];

    /**
     * @var string[]
     */
    private const TEMPERATURE_AIR_HINTS = [
        'air_temp',
        'temp_air',
        'ambient_temp',
        'climate_temp',
        'canopy_temp',
    ];

    /**
     * @var string[]
     */
    private const TEMPERATURE_WATER_HINTS = [
        'solution_temp',
        'temp_solution',
        'water_temp',
        'temp_water',
        'root_temp',
        'tank_temp',
        'reservoir_temp',
    ];

    /**
     * @var string[]
     */
    private const HUMIDITY_AIR_HINTS = [
        'air_rh',
        'rh_air',
        'humidity_air',
        'air_humidity',
        'ambient_rh',
        'ambient_humidity',
    ];

    public function getZoneSnapshot(int $zoneId, bool $onlyActiveSensors = false): array
    {
        return $this->getZoneSnapshots([$zoneId], $onlyActiveSensors)[$zoneId] ?? self::DEFAULT_SNAPSHOT;
    }

    public function getZoneSnapshots(array $zoneIds, bool $onlyActiveSensors = false): array
    {
        $zoneIds = array_values(array_unique(array_map('intval', $zoneIds)));
        if ($zoneIds === []) {
            return [];
        }

        $query = TelemetryLast::query()
            ->join('sensors', 'telemetry_last.sensor_id', '=', 'sensors.id')
            ->whereIn('sensors.zone_id', $zoneIds)
            ->whereNotNull('sensors.zone_id')
            ->select([
                'sensors.zone_id',
                'sensors.id as sensor_id',
                'sensors.label as channel',
                'sensors.type as metric_type',
                'telemetry_last.last_value as value',
                'telemetry_last.last_ts',
                'telemetry_last.updated_at',
            ])
            ->orderByRaw('telemetry_last.last_ts DESC NULLS LAST')
            ->orderByRaw('telemetry_last.updated_at DESC NULLS LAST')
            ->orderByDesc('sensors.id');

        if ($onlyActiveSensors) {
            $query->where('sensors.is_active', true);
        }

        return $this->summarizeRowsByZone($query->get());
    }

    /**
     * @return array<int, array<string, float|string|null>>
     */
    public function summarizeRowsByZone(iterable $rows): array
    {
        $grouped = [];

        foreach ($rows as $row) {
            $zoneId = isset($row->zone_id) ? (int) $row->zone_id : null;
            if (! $zoneId) {
                continue;
            }

            if (! isset($grouped[$zoneId])) {
                $grouped[$zoneId] = [];
            }

            $grouped[$zoneId][] = $row;
        }

        $snapshots = [];
        foreach ($grouped as $zoneId => $zoneRows) {
            $snapshots[$zoneId] = $this->summarizeRows(collect($zoneRows));
        }

        return $snapshots;
    }

    /**
     * @param  iterable<object|array<string, mixed>>  $rows
     * @return array<string, float|string|null>
     */
    public function summarizeRows(iterable $rows): array
    {
        $snapshot = self::DEFAULT_SNAPSHOT;
        $winners = [];

        foreach ($rows as $row) {
            $canonicalMetric = $this->canonicalMetric(
                $this->readString($row, 'metric_type'),
                $this->readString($row, 'channel')
            );

            if ($canonicalMetric === null) {
                continue;
            }

            $candidate = [
                'value' => $this->readFloat($row, 'value'),
                'priority' => $this->metricPriority($canonicalMetric, $this->readString($row, 'channel')),
                'last_ts' => $this->toTimestamp($this->readValue($row, 'last_ts')),
                'updated_at' => $this->toTimestamp($this->readValue($row, 'updated_at')),
                'sensor_id' => (int) ($this->readValue($row, 'sensor_id') ?? 0),
            ];

            if (! isset($winners[$canonicalMetric]) || $this->isBetterCandidate($candidate, $winners[$canonicalMetric])) {
                $winners[$canonicalMetric] = $candidate;
            }
        }

        $lastUpdatedTs = null;
        foreach ($winners as $metric => $candidate) {
            $snapshot[$metric] = $candidate['value'];
            $candidateTs = $candidate['last_ts'] ?: $candidate['updated_at'];
            if ($candidateTs !== null && ($lastUpdatedTs === null || $candidateTs > $lastUpdatedTs)) {
                $lastUpdatedTs = $candidateTs;
            }
        }

        if ($lastUpdatedTs !== null) {
            $snapshot['last_updated'] = gmdate('c', $lastUpdatedTs);
        }

        return $snapshot;
    }

    /**
     * @return string[]
     */
    public function getPreferredChannels(int $zoneId, string $metric, bool $onlyActiveSensors = false): array
    {
        $canonicalMetric = $this->canonicalMetric($metric, null);
        if ($canonicalMetric === null) {
            return [];
        }

        $query = Sensor::query()
            ->where('zone_id', $zoneId)
            ->select(['label as channel', 'type as metric_type']);

        if ($onlyActiveSensors) {
            $query->where('is_active', true);
        }

        $rows = $query->get();

        $bestPriority = null;
        $channels = [];

        foreach ($rows as $row) {
            if ($this->canonicalMetric($row->metric_type, $row->channel) !== $canonicalMetric) {
                continue;
            }

            $priority = $this->metricPriority($canonicalMetric, $row->channel);
            if ($bestPriority === null || $priority > $bestPriority) {
                $bestPriority = $priority;
                $channels = [];
            }

            if ($priority === $bestPriority && is_string($row->channel) && $row->channel !== '') {
                $channels[] = $row->channel;
            }
        }

        return array_values(array_unique($channels));
    }

    /**
     * @return string[]
     */
    public function metricAliases(string $metric): array
    {
        $canonicalMetric = $this->canonicalMetric($metric, null);

        return match ($canonicalMetric) {
            'ph' => ['PH'],
            'ec' => ['EC'],
            'temperature' => ['TEMPERATURE', 'TEMP_AIR', 'AIR_TEMP'],
            'humidity' => ['HUMIDITY', 'AIR_RH', 'HUMIDITY_AIR'],
            'co2' => ['CO2', 'CO2_PPM'],
            default => [],
        };
    }

    private function canonicalMetric(?string $metricType, ?string $channel): ?string
    {
        $metric = strtoupper(trim((string) $metricType));
        $channelKey = $this->normalizeChannel($channel);

        return match (true) {
            $metric === 'PH', str_contains($channelKey, 'ph') => 'ph',
            $metric === 'EC', preg_match('/(^|_)ec($|_)/', $channelKey) === 1 => 'ec',
            in_array($metric, ['TEMPERATURE', 'TEMP_AIR', 'AIR_TEMP'], true), str_contains($channelKey, 'temp') => 'temperature',
            in_array($metric, ['HUMIDITY', 'AIR_RH', 'HUMIDITY_AIR'], true), str_contains($channelKey, 'humid'), str_contains($channelKey, '_rh'), str_starts_with($channelKey, 'rh_') => 'humidity',
            in_array($metric, ['CO2', 'CO2_PPM'], true), str_contains($channelKey, 'co2') => 'co2',
            default => null,
        };
    }

    private function metricPriority(string $canonicalMetric, ?string $channel): int
    {
        $channelKey = $this->normalizeChannel($channel);

        return match ($canonicalMetric) {
            'temperature' => $this->temperaturePriority($channelKey),
            'humidity' => $this->humidityPriority($channelKey),
            default => 100,
        };
    }

    private function temperaturePriority(string $channel): int
    {
        if ($channel === '') {
            return 50;
        }

        if ($this->containsAny($channel, self::TEMPERATURE_AIR_HINTS)) {
            return 300;
        }

        if (in_array($channel, ['temperature', 'temp'], true)) {
            return 250;
        }

        if ($this->containsAny($channel, self::TEMPERATURE_WATER_HINTS)) {
            return 100;
        }

        return 200;
    }

    private function humidityPriority(string $channel): int
    {
        if ($channel === '') {
            return 50;
        }

        if ($this->containsAny($channel, self::HUMIDITY_AIR_HINTS)) {
            return 300;
        }

        if (in_array($channel, ['humidity', 'rh'], true)) {
            return 250;
        }

        return 200;
    }

    /**
     * @param  array<string, float|int|null>  $candidate
     * @param  array<string, float|int|null>  $current
     */
    private function isBetterCandidate(array $candidate, array $current): bool
    {
        if ($candidate['value'] !== null && $current['value'] === null) {
            return true;
        }

        if ($candidate['value'] === null && $current['value'] !== null) {
            return false;
        }

        if ($candidate['priority'] !== $current['priority']) {
            return $candidate['priority'] > $current['priority'];
        }

        if ($candidate['last_ts'] !== $current['last_ts']) {
            return ($candidate['last_ts'] ?? 0) > ($current['last_ts'] ?? 0);
        }

        if ($candidate['updated_at'] !== $current['updated_at']) {
            return ($candidate['updated_at'] ?? 0) > ($current['updated_at'] ?? 0);
        }

        return ($candidate['sensor_id'] ?? 0) > ($current['sensor_id'] ?? 0);
    }

    private function containsAny(string $haystack, array $needles): bool
    {
        foreach ($needles as $needle) {
            if (str_contains($haystack, $needle)) {
                return true;
            }
        }

        return false;
    }

    private function normalizeChannel(?string $channel): string
    {
        return strtolower(trim((string) $channel));
    }

    private function readString(object|array $row, string $key): ?string
    {
        $value = $this->readValue($row, $key);

        return is_string($value) ? $value : null;
    }

    private function readFloat(object|array $row, string $key): ?float
    {
        $value = $this->readValue($row, $key);

        return is_numeric($value) ? (float) $value : null;
    }

    private function readValue(object|array $row, string $key): mixed
    {
        if (is_array($row)) {
            return $row[$key] ?? null;
        }

        return $row->{$key} ?? null;
    }

    private function toTimestamp(mixed $value): ?int
    {
        if ($value instanceof \DateTimeInterface) {
            return $value->getTimestamp();
        }

        if (! is_string($value) || trim($value) === '') {
            return null;
        }

        $timestamp = strtotime($value);

        return $timestamp === false ? null : $timestamp;
    }
}
