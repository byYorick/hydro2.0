<?php

namespace App\Services\CropDay;

use App\Models\Zone;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

/**
 * Read-only интеграл DLI за местные сутки. Ничего не пишет.
 */
final class DliDayBalance
{
    /** @var list<string> */
    private const LUX_MAIN_CHANNELS = ['light', 'light_level', 'lux_main'];

    /** @var list<string> */
    private const EXPLICIT_KEYS = ['sensor_channel', 'light_channel', 'source_channel', 'outside_channel'];

    /**
     * @param  array{start: string, end: string}  $window
     * @return array{dli_mol: float|null, dli_status: string}
     */
    public function forZone(Zone $zone, array $window): array
    {
        $target = $this->activeTarget((int) $zone->id);
        $channel = $this->lightChannel((int) $zone->id, $this->explicitChannel((int) $zone->id));
        $unit = $channel['unit'] ?? '';
        $samples = [];
        if (DliIntegral::isPpfdUnit($unit) && $channel['sensor_id'] !== null) {
            $samples = $this->samples((int) $channel['sensor_id'], (int) $zone->id, $window['start'], $window['end']);
        }
        $integral = DliIntegral::isPpfdUnit($unit)
            ? DliIntegral::integrate($samples)
            : ['dli_mol' => null, 'status' => 'sensor_unavailable'];

        if ($target === null) {
            return [
                'dli_mol' => $integral['status'] === 'ok' ? $integral['dli_mol'] : null,
                'dli_status' => 'not_configured',
            ];
        }
        if ($integral['status'] === 'sensor_unavailable') {
            return ['dli_mol' => null, 'dli_status' => 'sensor_unavailable'];
        }
        if ($integral['status'] === 'gap') {
            return ['dli_mol' => null, 'dli_status' => 'gap'];
        }

        $mol = (float) $integral['dli_mol'];

        return [
            'dli_mol' => $mol,
            'dli_status' => $mol >= $target ? 'capped' : 'within_target',
        ];
    }

    private function activeTarget(int $zoneId): ?float
    {
        $row = DB::selectOne(
            "SELECT gcp.dli_target
             FROM grow_cycles AS gc
             INNER JOIN grow_cycle_phases AS gcp
                ON gcp.id = gc.current_phase_id
             WHERE gc.zone_id = ?
               AND gc.status IN ('RUNNING', 'PAUSED', 'PLANNED')
             ORDER BY
                CASE
                    WHEN gc.status = 'RUNNING' THEN 0
                    WHEN gc.status = 'PAUSED' THEN 1
                    WHEN gc.status = 'PLANNED' THEN 2
                    ELSE 3
                END,
                gc.id DESC
             LIMIT 1",
            [$zoneId],
        );
        if ($row === null || $row->dli_target === null || ! is_numeric($row->dli_target)) {
            return null;
        }
        $target = (float) $row->dli_target;

        return $target > 0 ? $target : null;
    }

    private function explicitChannel(int $zoneId): ?string
    {
        $row = DB::selectOne(
            "SELECT gcp.extensions
             FROM grow_cycles AS gc
             INNER JOIN grow_cycle_phases AS gcp
                ON gcp.id = gc.current_phase_id
             WHERE gc.zone_id = ?
               AND gc.status IN ('RUNNING', 'PAUSED', 'PLANNED')
             ORDER BY
                CASE
                    WHEN gc.status = 'RUNNING' THEN 0
                    WHEN gc.status = 'PAUSED' THEN 1
                    WHEN gc.status = 'PLANNED' THEN 2
                    ELSE 3
                END,
                gc.id DESC
             LIMIT 1",
            [$zoneId],
        );
        if ($row === null || $row->extensions === null) {
            return null;
        }
        $extensions = is_string($row->extensions) ? json_decode($row->extensions, true) : $row->extensions;
        if (! is_array($extensions)) {
            return null;
        }
        $lighting = $extensions['targets']['lighting'] ?? $extensions['lighting'] ?? null;
        if (! is_array($lighting)) {
            return null;
        }
        foreach (self::EXPLICIT_KEYS as $key) {
            $raw = $lighting[$key] ?? null;
            if (is_string($raw) && trim($raw) !== '') {
                return strtolower(trim($raw));
            }
        }

        return null;
    }

    /**
     * @return array{unit: string, sensor_id: int|null}
     */
    private function lightChannel(int $zoneId, ?string $explicit): array
    {
        $rows = DB::select(
            "SELECT
                nc.id,
                LOWER(COALESCE(nc.channel, '')) AS channel,
                nc.unit,
                nc.config,
                UPPER(COALESCE(nc.metric, '')) AS metric,
                LOWER(COALESCE(s.scope, '')) AS scope,
                s.id AS sensor_id
             FROM nodes AS n
             INNER JOIN node_channels AS nc
                ON nc.node_id = n.id
             LEFT JOIN sensors AS s
                ON s.node_id = n.id
               AND s.zone_id = n.zone_id
               AND s.is_active IS TRUE
               AND s.label = nc.channel
             WHERE n.zone_id = ?
               AND COALESCE(nc.is_active, TRUE) = TRUE
               AND UPPER(TRIM(COALESCE(nc.type, ''))) = 'SENSOR'
             ORDER BY nc.id ASC",
            [$zoneId],
        );

        $chosen = null;
        $rank = PHP_INT_MAX;
        foreach ($rows as $row) {
            $channel = strtolower((string) $row->channel);
            $metric = strtoupper((string) $row->metric);
            $scope = strtolower((string) $row->scope);
            $outside = in_array($channel, ['outside_light', 'out_light', 'outdoor_light'], true)
                || $metric === 'OUTSIDE_LIGHT'
                || $scope === 'outside';
            if ($explicit !== null) {
                if ($channel !== $explicit && $metric !== strtoupper($explicit)) {
                    continue;
                }
                $preference = 0;
            } else {
                if ($outside) {
                    continue;
                }
                if (! in_array($channel, self::LUX_MAIN_CHANNELS, true) && $metric !== 'LIGHT_INTENSITY') {
                    continue;
                }
                $preference = array_search($channel, self::LUX_MAIN_CHANNELS, true);
                $preference = $preference === false ? count(self::LUX_MAIN_CHANNELS) : (int) $preference;
            }
            $sortId = (int) $row->id;
            $score = ($preference * 1_000_000) + $sortId;
            if ($score < $rank) {
                $rank = $score;
                $chosen = $row;
            }
        }
        if ($chosen === null) {
            return ['unit' => '', 'sensor_id' => null];
        }

        return [
            'unit' => DliIntegral::configuredUnit($chosen->unit, $chosen->config),
            'sensor_id' => $chosen->sensor_id !== null ? (int) $chosen->sensor_id : null,
        ];
    }

    /**
     * @return list<array{ts: int, value: float}>
     */
    private function samples(int $sensorId, int $zoneId, string $start, string $end): array
    {
        $rows = DB::select(
            'SELECT ts, value
             FROM telemetry_samples
             WHERE sensor_id = ?
               AND zone_id = ?
               AND ts >= ?
               AND ts <= ?
             ORDER BY ts ASC',
            [$sensorId, $zoneId, $start, $end],
        );
        $points = [];
        foreach ($rows as $row) {
            $points[] = [
                'ts' => Carbon::parse((string) $row->ts, 'UTC')->getTimestamp(),
                'value' => (float) $row->value,
            ];
        }

        return $points;
    }
}
