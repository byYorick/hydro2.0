<?php

namespace App\Services\AutomationScheduler;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Active zone hang hints from PostgreSQL (parity with ZoneAutomationObservabilityService thresholds).
 */
final class ZoneHangHintsQuery
{
    public const HINT_WAITING_COMMAND_STUCK = 'waiting_command_stuck';

    public const HINT_STAGE_DEADLINE_EXCEEDED = 'stage_deadline_exceeded';

    public const HINT_SCHEDULER_INTENT_PENDING = 'scheduler_intent_pending';

    public const HINT_SCHEDULER_INTENT_CLAIMED_STUCK = 'scheduler_intent_claimed_stuck';

    /**
     * @return list<array{code: string, zone_id: int}>
     */
    public function fetchActiveHints(): array
    {
        if (! Schema::hasTable('ae_tasks')) {
            return [];
        }

        $hints = [];
        foreach ($this->hintQueries() as $query) {
            if (! Schema::hasTable('zone_automation_intents') && str_starts_with($query['code'], 'scheduler_intent')) {
                continue;
            }

            $rows = DB::select($query['sql']);
            foreach ($rows as $row) {
                $zoneId = (int) ($row->zone_id ?? 0);
                if ($zoneId <= 0) {
                    continue;
                }

                $hints[] = [
                    'code' => $query['code'],
                    'zone_id' => $zoneId,
                ];
            }
        }

        return $hints;
    }

    public function alertCodeForHint(string $hintCode): string
    {
        return match ($hintCode) {
            self::HINT_STAGE_DEADLINE_EXCEEDED => 'ae3_stage_deadline_exceeded',
            self::HINT_WAITING_COMMAND_STUCK => 'biz_zone_hang_hint_waiting_command_stuck',
            self::HINT_SCHEDULER_INTENT_PENDING => 'biz_zone_hang_hint_scheduler_intent_pending',
            self::HINT_SCHEDULER_INTENT_CLAIMED_STUCK => 'biz_zone_hang_hint_scheduler_intent_claimed_stuck',
            default => 'biz_zone_hang_hint_'.str_replace('-', '_', $hintCode),
        };
    }

    public function dedupeKeyForHint(int $zoneId, string $hintCode): string
    {
        return sprintf('hang_hint|%s|zone:%d', $hintCode, $zoneId);
    }

    /**
     * @return list<string>
     */
    public function managedAlertCodes(): array
    {
        return array_values(array_unique(array_map(
            fn (string $hintCode): string => $this->alertCodeForHint($hintCode),
            $this->hintCodes(),
        )));
    }

    /**
     * @return list<string>
     */
    public function hintCodes(): array
    {
        return [
            self::HINT_WAITING_COMMAND_STUCK,
            self::HINT_STAGE_DEADLINE_EXCEEDED,
            self::HINT_SCHEDULER_INTENT_PENDING,
            self::HINT_SCHEDULER_INTENT_CLAIMED_STUCK,
        ];
    }

    /**
     * @return list<array{code: string, sql: string}>
     */
    private function hintQueries(): array
    {
        return [
            [
                'code' => self::HINT_WAITING_COMMAND_STUCK,
                'sql' => "
                    SELECT zone_id
                    FROM ae_tasks
                    WHERE status = 'waiting_command'
                      AND EXTRACT(EPOCH FROM (NOW() - updated_at)) >= 120
                ",
            ],
            [
                'code' => self::HINT_STAGE_DEADLINE_EXCEEDED,
                'sql' => "
                    SELECT zone_id
                    FROM ae_tasks
                    WHERE status IN ('claimed', 'running', 'waiting_command')
                      AND stage_deadline_at IS NOT NULL
                      AND stage_deadline_at < NOW()
                ",
            ],
            [
                'code' => self::HINT_SCHEDULER_INTENT_PENDING,
                'sql' => "
                    SELECT zone_id
                    FROM zone_automation_intents
                    WHERE status = 'pending'
                      AND EXTRACT(EPOCH FROM (NOW() - created_at)) >= 300
                ",
            ],
            [
                'code' => self::HINT_SCHEDULER_INTENT_CLAIMED_STUCK,
                'sql' => "
                    SELECT zone_id
                    FROM zone_automation_intents
                    WHERE status = 'claimed'
                      AND EXTRACT(EPOCH FROM (NOW() - updated_at)) >= 180
                ",
            ],
        ];
    }
}
