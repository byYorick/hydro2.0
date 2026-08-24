<?php

namespace App\Services;

use App\Models\Alert;
use App\Models\User;
use App\Models\Zone;
use App\Services\AutomationScheduler\ZoneHangHintsQuery;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;

class ZoneOperatorUnblockService
{
    /**
     * Алерты, которые снимают блок автоматики после безопасного сброса.
     * Конфиг-дыры (pid/correction/targets) не закрываем — их нужно чинить, не ack-ать.
     *
     * @var list<string>
     */
    private const ACK_CODES = [
        'biz_ae3_task_failed',
        'biz_prepare_recirculation_retry_exhausted',
        'biz_correction_exhausted',
        'biz_ph_correction_no_effect',
        'biz_ec_correction_no_effect',
        'ae3_stage_deadline_exceeded',
        'biz_zone_hang_hint_waiting_command_stuck',
        'biz_zone_hang_hint_scheduler_intent_pending',
        'biz_zone_hang_hint_scheduler_intent_claimed_stuck',
    ];

    public function __construct(
        private readonly AutomationRuntimeConfigService $runtimeConfig,
        private readonly AlertService $alerts,
        private readonly ZoneHangHintsQuery $hangHints,
    ) {}

    /**
     * @return array<string, mixed>
     *
     * @throws ConnectionException
     * @throws RequestException
     */
    public function unblock(Zone $zone, User $user, string $reason, string $source = 'frontend_operator_unblock'): array
    {
        $aePayload = $this->dispatchToAutomationEngine($zone->id, $user, $reason, $source);
        $acked = $this->acknowledgeEligibleAlerts($zone, $user, $reason);

        UnifiedDashboardService::invalidate();
        Cache::forget('zone_automation_state:'.$zone->id);

        $data = is_array($aePayload['data'] ?? null) ? $aePayload['data'] : [];
        $data['alerts_acked'] = $acked;

        return [
            'status' => 'ok',
            'data' => $data,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function dispatchToAutomationEngine(int $zoneId, User $user, string $reason, string $source): array
    {
        $cfg = $this->runtimeConfig->schedulerConfig();
        $apiUrl = (string) ($cfg['api_url'] ?? config('services.automation_engine.api_url'));
        $timeout = (float) ($cfg['timeout_sec'] ?? 5.0);
        $headers = [
            'X-Trace-Id' => Str::lower((string) Str::uuid()),
            'X-Scheduler-Id' => (string) ($cfg['scheduler_id'] ?? 'laravel-api'),
        ];
        $token = trim((string) ($cfg['token'] ?? ''));
        if ($token !== '') {
            $headers['Authorization'] = 'Bearer '.$token;
        }

        $response = Http::acceptJson()
            ->timeout($timeout)
            ->withHeaders($headers)
            ->post("{$apiUrl}/zones/{$zoneId}/operator-unblock", [
                'source' => $source,
                'reason' => $reason,
                'user_id' => $user->id,
                'user_role' => (string) ($user->role ?? ''),
            ]);

        $response->throw();
        $decoded = $response->json();
        if (! is_array($decoded)) {
            throw new \RuntimeException('automation_engine_invalid_payload');
        }

        return $decoded;
    }

    /**
     * @return list<int>
     */
    private function acknowledgeEligibleAlerts(Zone $zone, User $user, string $reason): array
    {
        $codes = array_values(array_unique(array_merge(
            self::ACK_CODES,
            $this->hangHints->managedAlertCodes(),
        )));

        $alerts = Alert::query()
            ->where('zone_id', $zone->id)
            ->whereNull('resolved_at')
            ->get();

        $acked = [];
        foreach ($alerts as $alert) {
            $code = strtolower(trim((string) ($alert->code ?? '')));
            if (! in_array($code, $codes, true)) {
                continue;
            }
            try {
                $this->alerts->acknowledge($alert, [
                    'actor_id' => $user->id,
                    'actor_role' => (string) ($user->role ?? ''),
                    'reason' => $reason,
                    'source' => 'operator_unblock',
                ]);
                $acked[] = (int) $alert->id;
            } catch (\DomainException) {
                continue;
            }
        }

        return $acked;
    }
}
