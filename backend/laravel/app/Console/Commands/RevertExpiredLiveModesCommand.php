<?php

namespace App\Console\Commands;

use App\Models\Zone;
use App\Models\ZoneConfigChange;
use Illuminate\Console\Command;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Auto-revert zones из config_mode=live → locked, когда TTL истёк.
 *
 * Phase 5: TTL фоновая команда. Регистрируется в routes/console.php
 * как `Schedule::command(...)->everyMinute()`.
 */
class RevertExpiredLiveModesCommand extends Command
{
    protected $signature = 'automation:revert-expired-live-modes
                            {--dry-run : Only report, не менять state}';

    protected $description = 'Переключает зоны с истёкшим live TTL обратно в locked.';

    public function handle(): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $now = Carbon::now();

        $candidateIds = Zone::where('config_mode', 'live')
            ->whereNotNull('live_until')
            ->where('live_until', '<', $now)
            ->pluck('id');

        if ($candidateIds->isEmpty()) {
            $this->info('Нет истёкших live зон.');
            return self::SUCCESS;
        }

        $this->info(sprintf(
            '%s истёкших live зон: %d',
            $dryRun ? '[DRY-RUN]' : 'Переключаю',
            $candidateIds->count(),
        ));

        $count = 0;
        foreach ($candidateIds as $zoneId) {
            if ($dryRun) {
                $zone = Zone::find($zoneId);
                $this->line(sprintf(
                    ' - zone_id=%d (live_until=%s, started=%s)',
                    $zoneId,
                    optional($zone?->live_until)->toIso8601String(),
                    optional($zone?->live_started_at)->toIso8601String() ?? '—',
                ));
                continue;
            }

            // Audit fix: lockForUpdate + double-check config_mode inside the
            // transaction. User's PATCH /extend may have moved us past TTL
            // between candidate select and this loop; skip those to avoid
            // double-audit rows / constraint violations.
            $reverted = DB::transaction(function () use ($zoneId, $now): ?Zone {
                $zone = Zone::lockForUpdate()->find($zoneId);
                if ($zone === null) {
                    return null;
                }
                if (($zone->config_mode ?? 'locked') !== 'live') {
                    return null;
                }
                if ($zone->live_until === null || $zone->live_until >= $now) {
                    return null;
                }
                $previousLiveUntil = $zone->live_until;

                $zone->forceFill([
                    'config_mode' => 'locked',
                    'live_until' => null,
                    'live_started_at' => null,
                    'config_mode_changed_at' => $now,
                    'config_mode_changed_by' => null,
                ])->save();

                ZoneConfigChange::create([
                    'zone_id' => $zone->id,
                    'revision' => (int) ($zone->config_revision ?? 1),
                    'namespace' => 'zone.config_mode',
                    'diff_json' => [
                        'from' => 'live',
                        'to' => 'locked',
                        'auto_reverted' => true,
                        'previous_live_until' => optional($previousLiveUntil)->toIso8601String(),
                    ],
                    'user_id' => null,
                    'reason' => 'auto-revert: live TTL expired',
                ]);

                DB::table('zone_events')->insert([
                    'zone_id' => $zone->id,
                    'type' => 'CONFIG_MODE_AUTO_REVERTED',
                    'payload_json' => json_encode([
                        'reason' => 'ttl_expired',
                        'previous_live_until' => optional($previousLiveUntil)->toIso8601String(),
                    ]),
                    'created_at' => $now,
                ]);
                return $zone;
            });
            if ($reverted === null) {
                // Race: user extended TTL / toggled locked before we got the lock.
                continue;
            }

            Log::info('zone.config_mode.auto_reverted', [
                'zone_id' => $reverted->id,
            ]);

            $count++;
        }

        $this->info(sprintf('Готово: %d зон переключено в locked.', $count));
        return self::SUCCESS;
    }
}
