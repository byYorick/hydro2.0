<?php

namespace App\Services;

use App\Models\DeviceNode;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\Facades\Schema;

/**
 * Предохранители ручных команд: E-STOP, online узла, доза, interlock, rate limit.
 */
class ManualCommandSafetyService
{
    private const ZONE_ACTUATORS = [
        'FORCE_IRRIGATION',
        'FORCE_PH_CONTROL',
        'FORCE_EC_CONTROL',
        'FORCE_LIGHTING',
        'FORCE_CLIMATE',
    ];

    public function __construct(
        private readonly ZoneEstopService $estop,
        private readonly Ae3ZoneLeaseGuard $leaseGuard,
        private readonly ManualDoseGuard $doses,
        private readonly SafetyAuditLogger $audit,
    ) {}

    /**
     * @param  array<string, mixed>  $params
     */
    public function inspectNode(
        DeviceNode $node,
        string $cmd,
        array $params,
        ?string $channel,
        ?User $user,
    ): ManualCommandDecision {
        if (strtolower((string) $node->status) !== 'online') {
            return $this->reject($node->zone, $user, 'node_offline', 'Узел не в сети. Команда не отправлена.', 409, [
                'command' => $cmd,
                'channel' => $channel,
                'node_uid' => $node->uid,
                'node_status' => $node->status,
            ]);
        }

        if (! $this->leaseGuard->shouldBlockOperatorNodeCommand($cmd, $params)) {
            return ManualCommandDecision::allow();
        }

        $zone = $node->zone_id ? ($node->relationLoaded('zone') ? $node->zone : Zone::query()->find($node->zone_id)) : null;

        return $this->inspectActuator(
            $zone instanceof Zone ? $zone : null,
            $user,
            strtolower(trim($cmd)),
            $params,
            $channel,
            $node,
        );
    }

    /**
     * @param  array<string, mixed>  $params
     */
    public function inspectZone(
        Zone $zone,
        string $type,
        array $params,
        ?string $nodeUid,
        ?string $channel,
        ?User $user,
    ): ManualCommandDecision {
        $normalized = strtoupper(trim($type));
        $device = strtolower(trim($type));
        $isActuator = in_array($normalized, self::ZONE_ACTUATORS, true)
            || in_array($device, ['dose', 'run_pump', 'set_relay', 'set_state', 'set_pwm', 'set_position', 'calibrate'], true);

        if (! $isActuator && ! $this->doses->hasDoseFields($params)) {
            return ManualCommandDecision::allow();
        }

        if (in_array($device, ['set_relay', 'set_state', 'set_pwm'], true)
            && ! $this->leaseGuard->shouldBlockOperatorNodeCommand($device, $params)) {
            return ManualCommandDecision::allow();
        }

        $node = null;
        if (is_string($nodeUid) && $nodeUid !== '') {
            $node = DeviceNode::query()->where('uid', $nodeUid)->where('zone_id', $zone->id)->first();
            if ($node === null || strtolower((string) $node->status) !== 'online') {
                return $this->reject($zone, $user, 'node_offline', 'Целевой узел зоны не найден или не в сети.', 409, [
                    'command' => $type,
                    'node_uid' => $node?->uid ?? $nodeUid,
                    'node_status' => $node?->status,
                ]);
            }
        }

        $command = $normalized === 'FORCE_IRRIGATION' ? 'force_irrigation' : $device;

        return $this->inspectActuator($zone, $user, $command, $params, $channel, $node);
    }

    /**
     * @param  array<string, mixed>  $params
     */
    private function inspectActuator(
        ?Zone $zone,
        ?User $user,
        string $command,
        array $params,
        ?string $channel,
        ?DeviceNode $node,
    ): ManualCommandDecision {
        if ($zone instanceof Zone && $this->estop->status($zone)['active']) {
            $status = $this->estop->status($zone);

            return $this->reject($zone, $user, 'estop_active', 'Аварийный стоп активен на зоне. Включающие команды отклонены до снятия E-STOP.', 409, [
                'command' => $command,
                'channel' => $channel,
                'node_uid' => $status['node_uid'] ?? $node?->uid,
                'estop_source' => $status['source'],
            ]);
        }

        $doseDecision = $this->doses->check($zone, $user, $command, $params, $channel, $node?->type);
        if ($doseDecision !== null) {
            return $doseDecision;
        }

        if ($zone instanceof Zone && $this->isIrrigationStart($command, $params, $channel)) {
            $guard = $this->doses->levelGuard($zone);
            if ($guard['stop_on_solution_min']) {
                $level = $this->solutionMinLevel($zone);
                if ($level !== null && $level < $guard['level_on_threshold']) {
                    return $this->reject($zone, $user, 'solution_level_interlock', 'Полив и насос раствора заблокированы: уровень раствора ниже минимума.', 409, [
                        'command' => $command,
                        'channel' => $channel,
                        'solution_min' => $level,
                        'threshold' => $guard['level_on_threshold'],
                    ]);
                }
            }
        }

        if ($zone instanceof Zone) {
            $limited = $this->consumeRateLimit($zone, $user);
            if ($limited !== null) {
                return $this->reject($zone, $user, 'manual_command_rate_limited', 'Слишком много ручных команд в эту зону. Повторите позже.', 429, [
                    'command' => $command,
                    'retry_after_sec' => $limited,
                ]);
            }
        }

        return ManualCommandDecision::allow();
    }

    /**
     * @param  array<string, mixed>  $params
     */
    private function isIrrigationStart(string $command, array $params, ?string $channel): bool
    {
        if ($command === 'force_irrigation') {
            return true;
        }
        if (! $this->doses->isIrrigationChannel($channel)) {
            return false;
        }
        if ($command === 'run_pump') {
            return true;
        }

        return in_array($command, ['set_relay', 'set_state'], true)
            && $this->leaseGuard->shouldBlockOperatorNodeCommand($command, $params);
    }

    private function solutionMinLevel(Zone $zone): ?float
    {
        if (! Schema::hasTable('telemetry_last') || ! Schema::hasTable('sensors')) {
            return null;
        }

        $row = DB::table('telemetry_last')
            ->join('sensors', 'telemetry_last.sensor_id', '=', 'sensors.id')
            ->where('sensors.zone_id', $zone->id)
            ->where('sensors.type', 'WATER_LEVEL')
            ->where(function ($query): void {
                $query->where('sensors.label', 'ilike', '%solution_min%')
                    ->orWhere('sensors.label', 'ilike', '%level_solution_min%')
                    ->orWhereRaw("COALESCE(sensors.specs->>'channel', '') ilike '%solution_min%'");
            })
            ->orderByDesc('telemetry_last.updated_at')
            ->first(['telemetry_last.last_value as value']);

        if ($row === null || ! is_numeric($row->value)) {
            return null;
        }

        return (float) $row->value;
    }

    private function consumeRateLimit(Zone $zone, ?User $user): ?int
    {
        $max = max(1, (int) config('manual_safety.rate_per_minute', 30));
        $key = 'manual-actuator:zone:'.$zone->id.':user:'.($user?->id ?? 0);
        if (RateLimiter::tooManyAttempts($key, $max)) {
            return RateLimiter::availableIn($key);
        }
        RateLimiter::hit($key, 60);

        return null;
    }

    /**
     * @param  array<string, mixed>  $context
     */
    private function reject(
        ?Zone $zone,
        ?User $user,
        string $code,
        string $message,
        int $status,
        array $context,
    ): ManualCommandDecision {
        if ($zone instanceof Zone) {
            $this->audit->write(
                'manual_command_rejected',
                (int) $zone->id,
                'rejected',
                array_merge($context, ['code' => $code]),
                $user,
                true,
                'MANUAL_COMMAND_REJECTED',
            );
        }

        return ManualCommandDecision::reject($code, $message, $status, ['data' => $context]);
    }
}
