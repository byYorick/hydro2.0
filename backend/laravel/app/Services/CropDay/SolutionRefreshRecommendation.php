<?php

namespace App\Services\CropDay;

use App\Services\AlertService;
use App\Services\ZoneEventRecorder;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Одна рекомендация подмены за 24 часа. Пишет только scheduler-dispatch.
 * GET состояния и decision gate AE сюда не вызываются и intent solution_change не создают.
 */
final class SolutionRefreshRecommendation
{
    public const EVENT_TYPE = 'SOLUTION_REFRESH_RECOMMENDED';

    public const ALERT_CODE = 'solution_refresh_recommended';

    public const METRIC_NAME = 'ae3_solution_refresh_recommended_total';

    public const METRIC_CACHE_KEY = 'metrics.ae3_solution_refresh_recommended_total';

    private const HOURLY_KEY = 'crop_day.solution_refresh.hourly_scan_at';

    private const CONSIDERED_KEY = 'crop_day.solution_refresh.considered_zone_ids';

    public function beginCycle(): void
    {
        Cache::put(self::CONSIDERED_KEY, [], now()->addHours(2));
    }

    public function considerWithIntent(int $zoneId): void
    {
        if ($zoneId <= 0) {
            return;
        }

        $this->markConsidered($zoneId);
        $this->evaluate($zoneId);
    }

    /**
     * Обход зон без intent полива или долива в этом проходе. Не чаще раза в час.
     *
     * @param  list<int>  $zoneIds
     */
    public function sweepUncovered(array $zoneIds): void
    {
        $considered = $this->consideredIds();
        $pending = [];
        foreach ($zoneIds as $zoneId) {
            $zoneId = (int) $zoneId;
            if ($zoneId > 0 && ! isset($considered[$zoneId])) {
                $pending[] = $zoneId;
            }
        }
        if ($pending === [] || ! $this->hourlyDue()) {
            return;
        }

        Cache::put(self::HOURLY_KEY, CarbonImmutable::now('UTC')->toIso8601String(), now()->addDays(2));
        foreach ($pending as $zoneId) {
            try {
                $this->evaluate($zoneId);
            } catch (\Throwable $e) {
                Log::warning('solution_refresh_recommendation_failed', [
                    'zone_id' => $zoneId,
                    'error' => $e->getMessage(),
                ]);
            }
        }
    }

    private function evaluate(int $zoneId): void
    {
        $thresholds = $this->thresholds($zoneId);
        if ($thresholds['age_days'] === null && $thresholds['topup_ml'] === null) {
            return;
        }

        $anchor = $this->anchor($zoneId);
        if ($anchor === null) {
            return;
        }

        $now = CarbonImmutable::now('UTC')->setMicroseconds(0);
        $ageExceeded = $thresholds['age_days'] !== null
            && $now->greaterThan($anchor['at']->addDays($thresholds['age_days']));
        $volume = $this->topupVolume($zoneId, $anchor['at'], $now);
        $volumeExceeded = $thresholds['topup_ml'] !== null
            && $volume['status'] === 'ok'
            && $volume['ml'] !== null
            && $volume['ml'] > $thresholds['topup_ml'];
        if (! $ageExceeded && ! $volumeExceeded) {
            return;
        }

        $trigger = match (true) {
            $ageExceeded && $volumeExceeded => 'age_and_topup',
            $ageExceeded => 'age',
            default => 'topup',
        };
        $payload = [
            'message' => 'Пора подменить раствор. Подмена сама не запускается.',
            'label' => 'Пора подменить раствор',
            'trigger' => $trigger,
            'anchor_at' => $anchor['at']->toIso8601String(),
            'anchor_source' => $anchor['source'],
            'solution_max_age_days' => $thresholds['age_days'],
            'solution_refresh_after_topup_ml' => $thresholds['topup_ml'],
            'topup_ml' => $volume['ml'],
            'topup_ml_status' => $volume['status'],
        ];

        $recorded = DB::transaction(function () use ($zoneId, $now, $payload): bool {
            if ($this->recentEventExists($zoneId, $now)) {
                return false;
            }

            $eventId = app(ZoneEventRecorder::class)->record(
                zoneId: $zoneId,
                type: self::EVENT_TYPE,
                payload: $payload,
            );
            if ($eventId === null) {
                return false;
            }

            app(AlertService::class)->createOrUpdateActive([
                'zone_id' => $zoneId,
                'source' => 'biz',
                'code' => self::ALERT_CODE,
                'type' => 'Solution refresh recommended',
                'status' => 'ACTIVE',
                'severity' => 'warning',
                'category' => 'operations',
                'details' => $payload,
            ]);

            return true;
        });
        if ($recorded) {
            $this->recordRecommendedMetric();
        }
    }

    /**
     * Один инкремент на записанное событие. GET состояния сюда не приходит.
     */
    private function recordRecommendedMetric(): void
    {
        try {
            $write = function (): void {
                $current = Cache::get(self::METRIC_CACHE_KEY, 0);
                $total = is_numeric($current) ? (int) $current : 0;
                Cache::forever(self::METRIC_CACHE_KEY, $total + 1);
            };
            $lock = Cache::lock(self::METRIC_CACHE_KEY.':lock', 5);
            if ($lock->get()) {
                try {
                    $write();
                } finally {
                    $lock->release();
                }

                return;
            }
            $write();
        } catch (\Throwable $e) {
            Log::warning('solution_refresh_recommended_metric_failed', [
                'error' => $e->getMessage(),
            ]);
        }
    }

    /**
     * @return array{age_days: int|null, topup_ml: float|null}
     */
    private function thresholds(int $zoneId): array
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
        $extensions = $this->decodeExtensions($row->extensions ?? null);

        return [
            'age_days' => $this->ageDays($extensions['solution_max_age_days'] ?? null),
            'topup_ml' => $this->topupMl($extensions['solution_refresh_after_topup_ml'] ?? null),
        ];
    }

    /**
     * @return array{at: CarbonImmutable, source: string}|null
     */
    private function anchor(int $zoneId): ?array
    {
        $change = DB::selectOne(
            "SELECT COALESCE(completed_at, updated_at) AS anchor_at
             FROM ae_tasks
             WHERE zone_id = ?
               AND task_type = 'solution_change'
               AND status = 'completed'
               AND COALESCE(completed_at, updated_at) IS NOT NULL
             ORDER BY COALESCE(completed_at, updated_at) DESC, id DESC
             LIMIT 1",
            [$zoneId],
        );
        $changedAt = $this->parseTime($change->anchor_at ?? null);
        if ($changedAt !== null) {
            return ['at' => $changedAt, 'source' => 'solution_change'];
        }

        $ready = DB::selectOne(
            "SELECT st.triggered_at
             FROM ae_stage_transitions AS st
             INNER JOIN ae_tasks AS t
                ON t.id = st.task_id
             WHERE t.zone_id = ?
               AND t.task_type = 'cycle_start'
               AND (
                    lower(COALESCE(st.workflow_phase, '')) = 'ready'
                    OR lower(st.to_stage) = 'complete_ready'
               )
             ORDER BY st.triggered_at DESC, st.id DESC
             LIMIT 1",
            [$zoneId],
        );
        $readyAt = $this->parseTime($ready->triggered_at ?? null);
        if ($readyAt === null) {
            return null;
        }

        return ['at' => $readyAt, 'source' => 'cycle_start_ready'];
    }

    /**
     * @return array{ml: float|null, status: string}
     */
    private function topupVolume(int $zoneId, CarbonImmutable $from, CarbonImmutable $to): array
    {
        $asOf = $to->format('Y-m-d H:i:s');
        $row = DB::selectOne(
            "SELECT
                COUNT(*) FILTER (WHERE cal.ml_per_sec IS NULL)::int AS missing_calibration,
                SUM((c.duration_ms::numeric / 1000.0) * cal.ml_per_sec) AS commanded_ml
             FROM commands AS c
             INNER JOIN ae_commands AS ac
                ON ac.external_id = c.id::text
             INNER JOIN ae_tasks AS t
                ON t.id = ac.task_id
               AND t.task_type = 'solution_topup'
             LEFT JOIN LATERAL (
                SELECT pc.ml_per_sec
                FROM node_channels AS nc
                INNER JOIN pump_calibrations AS pc
                    ON pc.node_channel_id = nc.id
                WHERE nc.node_id = c.node_id
                  AND nc.channel = c.channel
                  AND pc.is_active IS TRUE
                  AND pc.ml_per_sec IS NOT NULL
                  AND pc.valid_from <= ?
                  AND (pc.valid_to IS NULL OR pc.valid_to > ?)
                ORDER BY pc.valid_from DESC, pc.id DESC
                LIMIT 1
             ) AS cal ON TRUE
             WHERE c.status = 'DONE'
               AND c.zone_id = ?
               AND c.created_at >= ?
               AND c.created_at <= ?
               AND (
                    ac.planner_step = 'solution_topup'
                    OR ac.planner_step LIKE 'solution\\_topup%' ESCAPE '\\'
               )",
            [
                $asOf,
                $asOf,
                $zoneId,
                $from->format('Y-m-d H:i:s'),
                $asOf,
            ],
        );

        if ((int) ($row->missing_calibration ?? 0) > 0) {
            return ['ml' => null, 'status' => 'calibration_missing'];
        }

        $ml = $row === null || $row->commanded_ml === null
            ? 0.0
            : round((float) $row->commanded_ml, 6);

        return ['ml' => $ml, 'status' => 'ok'];
    }

    private function recentEventExists(int $zoneId, CarbonImmutable $now): bool
    {
        return DB::table('zone_events')
            ->where('zone_id', $zoneId)
            ->where('type', self::EVENT_TYPE)
            ->where('created_at', '>=', $now->subHours(24)->format('Y-m-d H:i:s'))
            ->exists();
    }

    /**
     * @return array<string, mixed>
     */
    private function decodeExtensions(mixed $raw): array
    {
        if (is_string($raw) && $raw !== '') {
            $raw = json_decode($raw, true);
        }
        if (is_string($raw) && $raw !== '') {
            $raw = json_decode($raw, true);
        }

        return is_array($raw) ? $raw : [];
    }

    private function ageDays(mixed $value): ?int
    {
        if (is_string($value)) {
            $value = trim($value);
            if ($value === '' || preg_match('/^\d+$/', $value) !== 1) {
                return null;
            }
            $value = (int) $value;
        }
        if (is_float($value)) {
            if (abs($value - round($value)) > 0.000001) {
                return null;
            }
            $value = (int) round($value);
        }
        if (! is_int($value) || $value < 1 || $value > 60) {
            return null;
        }

        return $value;
    }

    private function topupMl(mixed $value): ?float
    {
        if (is_string($value)) {
            $value = trim($value);
            if ($value === '' || ! is_numeric($value)) {
                return null;
            }
            $value = (float) $value;
        }
        if (is_int($value)) {
            $value = (float) $value;
        }
        if (! is_float($value) || ! is_finite($value) || $value <= 0) {
            return null;
        }

        return $value;
    }

    private function parseTime(mixed $value): ?CarbonImmutable
    {
        if ($value instanceof \DateTimeInterface) {
            return CarbonImmutable::parse($value->format('Y-m-d H:i:s'), 'UTC')->setMicroseconds(0);
        }
        if (! is_string($value) || trim($value) === '') {
            return null;
        }

        return CarbonImmutable::parse($value)->utc()->setMicroseconds(0);
    }

    private function hourlyDue(): bool
    {
        $raw = Cache::get(self::HOURLY_KEY);
        if (! is_string($raw) || trim($raw) === '') {
            return true;
        }
        try {
            $last = CarbonImmutable::parse($raw)->utc();
        } catch (\Throwable) {
            return true;
        }

        return $last->addHour()->lte(CarbonImmutable::now('UTC')->setMicroseconds(0));
    }

    private function markConsidered(int $zoneId): void
    {
        $ids = $this->consideredIds();
        $ids[$zoneId] = true;
        Cache::put(self::CONSIDERED_KEY, $ids, now()->addHours(2));
    }

    /**
     * @return array<int, true>
     */
    private function consideredIds(): array
    {
        $raw = Cache::get(self::CONSIDERED_KEY, []);
        if (! is_array($raw)) {
            return [];
        }

        $ids = [];
        foreach ($raw as $zoneId => $marked) {
            if ($marked && (int) $zoneId > 0) {
                $ids[(int) $zoneId] = true;
            }
        }

        return $ids;
    }
}
