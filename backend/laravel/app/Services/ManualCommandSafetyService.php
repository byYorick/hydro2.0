<?php

namespace App\Services;

use App\Models\AutomationConfigDocument;
use App\Models\Command;
use App\Models\DeviceNode;
use App\Models\User;
use App\Models\Zone;
use App\Support\Automation\ZoneCorrectionResolvedConfigBuilder;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\Facades\Schema;

/**
 * Те же предохранители, что AE3 ставит перед дозой и поливом,
 * плюс отказ, если целевой узел не online, суммарная доза за окно
 * и rate limit ручных включающих команд.
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

    private const PH_HINTS = ['pump_acid', 'pump_base', 'ph_up', 'ph_down', 'pump_ph'];

    private const EC_HINTS = ['pump_a', 'pump_b', 'pump_c', 'pump_d', 'npk', 'calcium', 'magnesium', 'micro'];

    private const IRRIGATION_HINTS = ['pump_main', 'valve_irrigation', 'valve_solution', 'valve_clean'];

    public function __construct(
        private readonly ZoneEstopService $estop,
        private readonly Ae3ZoneLeaseGuard $leaseGuard,
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
            zone: $zone instanceof Zone ? $zone : null,
            user: $user,
            command: strtolower(trim($cmd)),
            params: $params,
            channel: $channel,
            node: $node,
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
        $doseFields = $this->hasDoseFields($params);
        $isActuator = in_array($normalized, self::ZONE_ACTUATORS, true)
            || in_array($device, ['dose', 'run_pump', 'set_relay', 'set_state', 'set_pwm', 'set_position', 'calibrate'], true);

        if (! $isActuator && ! $doseFields) {
            return ManualCommandDecision::allow();
        }

        if ($this->leaseGuard->shouldBlockOperatorNodeCommand($device, $params) === false
            && in_array($device, ['set_relay', 'set_state', 'set_pwm'], true)) {
            return ManualCommandDecision::allow();
        }

        $node = null;
        if (is_string($nodeUid) && $nodeUid !== '') {
            $node = DeviceNode::query()->where('uid', $nodeUid)->where('zone_id', $zone->id)->first();
            if ($node === null) {
                return $this->reject($zone, $user, 'node_offline', 'Целевой узел зоны не найден или не в сети.', 409, [
                    'command' => $type,
                    'node_uid' => $nodeUid,
                ]);
            }
            if (strtolower((string) $node->status) !== 'online') {
                return $this->reject($zone, $user, 'node_offline', 'Узел не в сети. Команда не отправлена.', 409, [
                    'command' => $type,
                    'node_uid' => $node->uid,
                    'node_status' => $node->status,
                ]);
            }
        }

        return $this->inspectActuator(
            zone: $zone,
            user: $user,
            command: $normalized === 'FORCE_IRRIGATION' ? 'force_irrigation' : $device,
            params: $params,
            channel: $channel,
            node: $node,
        );
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

        $limits = $this->limitsFor($zone);
        $kind = $this->doseKind($command, $channel, $node?->type);
        $ml = $this->numeric($params['ml'] ?? $params['dose_ml'] ?? null);
        $durationMs = $this->durationMs($params);

        if ($ml !== null || ($durationMs !== null && in_array($command, ['dose', 'run_pump', 'force_ph_control', 'force_ec_control'], true))) {
            $doseDecision = $this->checkDose($zone, $user, $command, $channel, $kind, $ml, $durationMs, $limits);
            if ($doseDecision !== null) {
                return $doseDecision;
            }
        }

        if ($zone instanceof Zone && $this->isIrrigationStart($command, $params, $channel) && $limits['stop_on_solution_min']) {
            $level = $this->solutionMinLevel($zone);
            if ($level !== null && $level < $limits['level_on_threshold']) {
                return $this->reject($zone, $user, 'solution_level_interlock', 'Полив и насос раствора заблокированы: уровень раствора ниже минимума.', 409, [
                    'command' => $command,
                    'channel' => $channel,
                    'solution_min' => $level,
                    'threshold' => $limits['level_on_threshold'],
                ]);
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
     * @param  array{ph_max_ml: float, ec_max_ml: float, ph_interval_sec: int, ec_interval_sec: int, ph_attempts: int, ec_attempts: int, min_dose_ms: int, max_dose_ms: int, level_on_threshold: float, stop_on_solution_min: bool}  $limits
     */
    private function checkDose(
        ?Zone $zone,
        ?User $user,
        string $command,
        ?string $channel,
        ?string $kind,
        ?float $ml,
        ?int $durationMs,
        array $limits,
    ): ?ManualCommandDecision {
        if ($ml !== null && $ml <= 0) {
            return $this->reject($zone, $user, 'dose_limit_exceeded', 'Объём дозы должен быть положительным.', 422, [
                'command' => $command,
                'ml' => $ml,
            ]);
        }
        if ($ml !== null && $ml > 500) {
            return $this->reject($zone, $user, 'dose_limit_exceeded', 'Объём дозы превышает транспортный потолок.', 422, [
                'command' => $command,
                'ml' => $ml,
                'limit_ml' => 500,
            ]);
        }
        if ($durationMs !== null && $durationMs <= 0) {
            return $this->reject($zone, $user, 'dose_limit_exceeded', 'Длительность команды должна быть положительной.', 422, [
                'command' => $command,
                'duration_ms' => $durationMs,
            ]);
        }
        if ($durationMs !== null && $durationMs > 300_000 && $kind !== 'irrigation') {
            return $this->reject($zone, $user, 'dose_limit_exceeded', 'Длительность превышает транспортный потолок.', 422, [
                'command' => $command,
                'duration_ms' => $durationMs,
                'limit_ms' => 300_000,
            ]);
        }

        $chemical = in_array($kind, ['ph', 'ec', 'unknown'], true) || $command === 'dose';
        if (! $chemical) {
            if ($kind === 'irrigation' && $durationMs !== null && $durationMs > 3_600_000) {
                return $this->reject($zone, $user, 'dose_limit_exceeded', 'Длительность полива не может быть больше 3600 секунд.', 422, [
                    'command' => $command,
                    'duration_ms' => $durationMs,
                ]);
            }

            return null;
        }

        $cap = $kind === 'ec' ? $limits['ec_max_ml'] : $limits['ph_max_ml'];
        if ($ml !== null && $ml > $cap) {
            return $this->reject($zone, $user, 'dose_limit_exceeded', 'Доза больше разового лимита контроллера.', 422, [
                'command' => $command,
                'channel' => $channel,
                'ml' => $ml,
                'limit_ml' => $cap,
                'controller' => $kind === 'ec' ? 'ec' : 'ph',
            ]);
        }

        if ($durationMs !== null && $command !== 'force_irrigation') {
            if ($durationMs > $limits['max_dose_ms']) {
                return $this->reject($zone, $user, 'dose_limit_exceeded', 'Длительность дозы больше pump_calibration.max_dose_ms.', 422, [
                    'command' => $command,
                    'duration_ms' => $durationMs,
                    'limit_ms' => $limits['max_dose_ms'],
                ]);
            }
            if ($durationMs < $limits['min_dose_ms']) {
                return $this->reject($zone, $user, 'dose_below_min_dose_ms', 'Длительность дозы меньше минимального импульса насоса.', 422, [
                    'command' => $command,
                    'duration_ms' => $durationMs,
                    'min_dose_ms' => $limits['min_dose_ms'],
                ]);
            }
        }

        if (! $zone instanceof Zone) {
            return null;
        }

        $controller = $kind === 'ec' ? 'ec' : 'ph';
        $interval = $controller === 'ec' ? $limits['ec_interval_sec'] : $limits['ph_interval_sec'];
        $retryAfter = $this->doseIntervalRemaining($zone, $controller, $channel, $interval);
        if ($retryAfter > 0 && ($command === 'dose' || $ml !== null)) {
            return $this->reject($zone, $user, 'dose_interval_active', 'Следующая доза этого контура ещё не разрешена.', 409, [
                'command' => $command,
                'channel' => $channel,
                'controller' => $controller,
                'retry_after_sec' => $retryAfter,
                'min_interval_sec' => $interval,
            ]);
        }

        if ($ml !== null) {
            $attempts = $controller === 'ec' ? $limits['ec_attempts'] : $limits['ph_attempts'];
            $windowCap = $cap * max(1, $attempts);
            $used = $this->dosedMlInWindow($zone, $controller, $channel);
            if (($used + $ml) > $windowCap + 0.0001) {
                return $this->reject($zone, $user, 'dose_window_limit_exceeded', 'Суммарная доза зоны за окно превышает бюджет контроллера.', 422, [
                    'command' => $command,
                    'channel' => $channel,
                    'controller' => $controller,
                    'ml' => $ml,
                    'used_ml' => $used,
                    'limit_ml' => $windowCap,
                    'window_sec' => (int) config('manual_safety.dose_window_sec', 3600),
                ]);
            }
        }

        return null;
    }

    /**
     * @param  array<string, mixed>  $params
     */
    private function hasDoseFields(array $params): bool
    {
        return $this->numeric($params['ml'] ?? $params['dose_ml'] ?? null) !== null
            || $this->durationMs($params) !== null;
    }

    /**
     * @param  array<string, mixed>  $params
     */
    private function isIrrigationStart(string $command, array $params, ?string $channel): bool
    {
        if ($command === 'force_irrigation') {
            return true;
        }
        $channelName = strtolower((string) $channel);
        $irrigationChannel = $this->containsAny($channelName, self::IRRIGATION_HINTS);
        if ($command === 'run_pump') {
            return $irrigationChannel;
        }
        if (in_array($command, ['set_relay', 'set_state'], true) && $irrigationChannel) {
            return $this->leaseGuard->shouldBlockOperatorNodeCommand($command, $params);
        }

        return false;
    }

    private function doseKind(string $command, ?string $channel, ?string $nodeType): ?string
    {
        $channelName = strtolower((string) $channel);
        $type = strtolower((string) $nodeType);
        if ($command === 'force_irrigation' || $this->containsAny($channelName, self::IRRIGATION_HINTS)) {
            if ($command !== 'dose' && ! $this->containsAny($channelName, self::PH_HINTS) && ! $this->containsAny($channelName, self::EC_HINTS)) {
                return 'irrigation';
            }
        }
        if ($command === 'force_ph_control' || str_contains($type, 'ph') || $this->containsAny($channelName, self::PH_HINTS)) {
            return 'ph';
        }
        if ($command === 'force_ec_control' || ($type !== '' && str_contains($type, 'ec')) || $this->containsAny($channelName, self::EC_HINTS)) {
            return 'ec';
        }
        if ($command === 'dose') {
            return 'unknown';
        }

        return null;
    }

    /**
     * @param  list<string>  $needles
     */
    private function containsAny(string $haystack, array $needles): bool
    {
        foreach ($needles as $needle) {
            if ($needle !== '' && str_contains($haystack, $needle)) {
                return true;
            }
        }

        return false;
    }

    private function doseIntervalRemaining(Zone $zone, string $controller, ?string $channel, int $intervalSec): int
    {
        if ($intervalSec <= 0 || ! Schema::hasTable('commands')) {
            return 0;
        }

        $latest = null;
        if (Schema::hasTable('pid_state')) {
            $pidAt = DB::table('pid_state')
                ->where('zone_id', $zone->id)
                ->where('pid_type', $controller)
                ->value('last_dose_at');
            if ($pidAt) {
                $latest = Carbon::parse($pidAt);
            }
        }

        $query = Command::query()
            ->where('zone_id', $zone->id)
            ->where('cmd', 'dose')
            ->where('status', Command::STATUS_DONE)
            ->where('created_at', '>=', now()->subSeconds($intervalSec));
        if (is_string($channel) && $channel !== '') {
            $query->where('channel', $channel);
        }
        $commandAt = $query->max('created_at');
        if ($commandAt) {
            $parsed = Carbon::parse($commandAt);
            if ($latest === null || $parsed->greaterThan($latest)) {
                $latest = $parsed;
            }
        }

        if ($latest === null || $latest->greaterThan(now())) {
            return $latest === null ? 0 : $intervalSec;
        }

        return max(0, $intervalSec - (int) $latest->diffInSeconds(now()));
    }

    private function dosedMlInWindow(Zone $zone, string $controller, ?string $channel): float
    {
        if (! Schema::hasTable('commands')) {
            return 0.0;
        }
        $window = max(1, (int) config('manual_safety.dose_window_sec', 3600));
        $rows = Command::query()
            ->where('zone_id', $zone->id)
            ->where('cmd', 'dose')
            ->where('created_at', '>=', now()->subSeconds($window))
            ->whereNotIn('status', [Command::STATUS_SEND_FAILED, Command::STATUS_INVALID])
            ->get(['params', 'channel']);

        $sum = 0.0;
        foreach ($rows as $row) {
            $rowChannel = is_string($row->channel) ? $row->channel : $channel;
            $rowKind = $this->doseKind('dose', $rowChannel, null);
            if ($controller === 'ec' && $rowKind !== 'ec') {
                continue;
            }
            if ($controller === 'ph' && $rowKind === 'ec') {
                continue;
            }
            $params = is_array($row->params) ? $row->params : [];
            $ml = $this->numeric($params['ml'] ?? $params['dose_ml'] ?? null);
            if ($ml !== null && $ml > 0) {
                $sum += $ml;
            }
        }

        return $sum;
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
     * @return array{ph_max_ml: float, ec_max_ml: float, ph_interval_sec: int, ec_interval_sec: int, ph_attempts: int, ec_attempts: int, min_dose_ms: int, max_dose_ms: int, level_on_threshold: float, stop_on_solution_min: bool}
     */
    private function limitsFor(?Zone $zone): array
    {
        $defaults = ZoneCorrectionConfigCatalog::defaults();
        $pump = SystemAutomationSettingsCatalog::defaults('pump_calibration');
        $limits = [
            'ph_max_ml' => (float) data_get($defaults, 'controllers.ph.max_dose_ml', 35),
            'ec_max_ml' => (float) data_get($defaults, 'controllers.ec.max_dose_ml', 80),
            'ph_interval_sec' => (int) data_get($defaults, 'controllers.ph.min_interval_sec', 20),
            'ec_interval_sec' => (int) data_get($defaults, 'controllers.ec.min_interval_sec', 25),
            'ph_attempts' => (int) data_get($defaults, 'retry.max_ph_correction_attempts', 8),
            'ec_attempts' => (int) data_get($defaults, 'retry.max_ec_correction_attempts', 8),
            'min_dose_ms' => (int) ($pump['min_dose_ms'] ?? 50),
            'max_dose_ms' => (int) ($pump['max_dose_ms'] ?? 60_000),
            'level_on_threshold' => (float) data_get($defaults, 'runtime.level_switch_on_threshold', 0.5),
            'stop_on_solution_min' => true,
        ];

        if (! $zone instanceof Zone || ! Schema::hasTable('automation_config_documents')) {
            return $limits;
        }

        try {
            $document = AutomationConfigDocument::query()
                ->where('namespace', AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION)
                ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
                ->where('scope_id', $zone->id)
                ->first();
            if ($document === null || ! is_array($document->payload)) {
                return $limits;
            }
            $resolved = app(ZoneCorrectionResolvedConfigBuilder::class)->buildFromPayload($document->payload);
            $phase = is_array($resolved['phases']['irrigation'] ?? null)
                ? $resolved['phases']['irrigation']
                : (is_array($resolved['base'] ?? null) ? $resolved['base'] : []);
            $limits['ph_max_ml'] = (float) data_get($phase, 'controllers.ph.max_dose_ml', $limits['ph_max_ml']);
            $limits['ec_max_ml'] = (float) data_get($phase, 'controllers.ec.max_dose_ml', $limits['ec_max_ml']);
            $limits['ph_interval_sec'] = (int) data_get($phase, 'controllers.ph.min_interval_sec', $limits['ph_interval_sec']);
            $limits['ec_interval_sec'] = (int) data_get($phase, 'controllers.ec.min_interval_sec', $limits['ec_interval_sec']);
            $limits['ph_attempts'] = (int) data_get($phase, 'retry.max_ph_correction_attempts', $limits['ph_attempts']);
            $limits['ec_attempts'] = (int) data_get($phase, 'retry.max_ec_correction_attempts', $limits['ec_attempts']);
            $limits['level_on_threshold'] = (float) data_get($phase, 'runtime.level_switch_on_threshold', $limits['level_on_threshold']);
            $pumpResolved = is_array($resolved['pump_calibration'] ?? null) ? $resolved['pump_calibration'] : [];
            if (isset($pumpResolved['max_dose_ms'])) {
                $limits['max_dose_ms'] = (int) $pumpResolved['max_dose_ms'];
            }
            if (isset($pumpResolved['min_dose_ms'])) {
                $limits['min_dose_ms'] = (int) $pumpResolved['min_dose_ms'];
            }
        } catch (\Throwable $exception) {
            report($exception);
        }

        return $limits;
    }

    /**
     * @param  array<string, mixed>  $params
     */
    private function durationMs(array $params): ?int
    {
        if (isset($params['duration_ms']) && is_numeric($params['duration_ms'])) {
            return (int) $params['duration_ms'];
        }
        if (isset($params['duration_sec']) && is_numeric($params['duration_sec'])) {
            return (int) round(((float) $params['duration_sec']) * 1000);
        }

        return null;
    }

    private function numeric(mixed $value): ?float
    {
        if (! is_numeric($value)) {
            return null;
        }

        return (float) $value;
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

        return ManualCommandDecision::reject($code, $message, $status, [
            'data' => $context,
        ]);
    }
}
