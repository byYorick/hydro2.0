<?php

namespace App\Console\Commands;

use App\Models\Alert;
use App\Services\AlertService;
use App\Services\AutomationScheduler\ZoneHangHintsQuery;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Log;

class BridgeZoneHangHints extends Command
{
    private const BRIDGE_COMPONENT = 'cron:automation:bridge-hang-hints';

    protected $signature = 'automation:bridge-hang-hints';

    protected $description = 'Bridge active zone hang hints from PostgreSQL into AlertService';

    public function __construct(
        private readonly AlertService $alertService,
        private readonly ZoneHangHintsQuery $hangHintsQuery,
    ) {
        parent::__construct();
    }

    public function handle(): int
    {
        $activeHintKeys = [];
        $upserted = 0;
        $resolved = 0;

        foreach ($this->hangHintsQuery->fetchActiveHints() as $hint) {
            $zoneId = (int) $hint['zone_id'];
            $hintCode = (string) $hint['code'];
            $alertCode = $this->hangHintsQuery->alertCodeForHint($hintCode);
            $dedupeKey = $this->hangHintsQuery->dedupeKeyForHint($zoneId, $hintCode);
            $activeHintKeys[$this->activeHintKey($zoneId, $hintCode)] = true;

            try {
                $this->alertService->createOrUpdateActive([
                    'zone_id' => $zoneId,
                    'source' => 'infra',
                    'code' => $alertCode,
                    'type' => $hintCode,
                    'severity' => $hintCode === ZoneHangHintsQuery::HINT_STAGE_DEADLINE_EXCEEDED
                        ? 'critical'
                        : 'warning',
                    'category' => 'operations',
                    'details' => [
                        'hang_hint_code' => $hintCode,
                        'dedupe_key' => $dedupeKey,
                        'component' => self::BRIDGE_COMPONENT,
                        'message' => sprintf('Active hang hint %s for zone %d', $hintCode, $zoneId),
                    ],
                ]);
                $upserted++;
            } catch (\Throwable $e) {
                Log::warning('Failed to bridge hang hint to AlertService', [
                    'zone_id' => $zoneId,
                    'hint_code' => $hintCode,
                    'alert_code' => $alertCode,
                    'error' => $e->getMessage(),
                ]);
            }
        }

        $bridgedAlerts = Alert::query()
            ->whereIn('code', $this->hangHintsQuery->managedAlertCodes())
            ->where('status', 'ACTIVE')
            ->whereRaw("details->>'component' = ?", [self::BRIDGE_COMPONENT])
            ->get(['id', 'zone_id', 'code', 'details']);

        foreach ($bridgedAlerts as $alert) {
            $details = is_array($alert->details) ? $alert->details : [];
            $hintCode = is_string($details['hang_hint_code'] ?? null) ? $details['hang_hint_code'] : null;
            $zoneId = (int) $alert->zone_id;
            if ($hintCode === null || $zoneId <= 0) {
                continue;
            }

            if (isset($activeHintKeys[$this->activeHintKey($zoneId, $hintCode)])) {
                continue;
            }

            $dedupeKey = is_string($details['dedupe_key'] ?? null)
                ? $details['dedupe_key']
                : $this->hangHintsQuery->dedupeKeyForHint($zoneId, $hintCode);

            try {
                $result = $this->alertService->resolveByCode($zoneId, (string) $alert->code, [
                    'resolved_by' => self::BRIDGE_COMPONENT,
                    'resolved_via' => 'auto',
                    'reason' => 'hang_hint_cleared',
                    'details' => [
                        'dedupe_key' => $dedupeKey,
                        'hang_hint_code' => $hintCode,
                    ],
                ]);

                if ($result['resolved'] ?? false) {
                    $resolved++;
                }
            } catch (\Throwable $e) {
                Log::warning('Failed to resolve bridged hang hint alert', [
                    'alert_id' => $alert->id,
                    'zone_id' => $zoneId,
                    'hint_code' => $hintCode,
                    'error' => $e->getMessage(),
                ]);
            }
        }

        $this->info(sprintf(
            'Hang hints bridge: %d active, %d upserted, %d resolved',
            count($activeHintKeys),
            $upserted,
            $resolved,
        ));

        return self::SUCCESS;
    }

    private function activeHintKey(int $zoneId, string $hintCode): string
    {
        return sprintf('%d|%s', $zoneId, $hintCode);
    }
}
