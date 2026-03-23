<?php

namespace App\Services;

use App\Models\Alert;
use App\Models\ChannelBinding;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Models\ZoneAutomationLogicProfile;
use App\Models\ZonePidConfig;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Сервис для проверки готовности зоны к запуску grow-cycle
 */
class ZoneReadinessService
{
    private const HARD_BLOCKING_ALERT_CODES = [
        'biz_zone_correction_config_missing',
        'biz_zone_dosing_calibration_missing',
    ];

    private const PH_REQUIRED_BINDINGS = [
        'ph_acid_pump',
        'ph_base_pump',
    ];

    private const EC_REQUIRED_BINDINGS = [
        'ec_npk_pump',
        'ec_calcium_pump',
        'ec_magnesium_pump',
        'ec_micro_pump',
    ];

    public function __construct(
        private readonly AutomationRuntimeConfigService $runtimeConfig
    ) {}

    /**
     * Получить список обязательных bindings для зоны.
     *
     * В E2E режиме возвращает пустой массив для гибкости тестирования.
     * В production режиме использует конфигурацию из config/zones.php.
     */
    private function getRequiredBindings(Zone $zone): array
    {
        // В E2E режиме strict-проверки можно отключать полностью для изолированных тестовых сценариев.
        $env = env('APP_ENV', 'production');
        if (config('zones.readiness.e2e_mode', false) || $env === 'e2e') {
            return [];
        }

        // Если strict_mode отключен - возвращаем пустой массив
        if (! config('zones.readiness.strict_mode', true)) {
            return [];
        }

        $configured = config('zones.readiness.required_bindings', ['main_pump', 'drain']);
        if (is_string($configured)) {
            $configured = array_filter(array_map('trim', explode(',', $configured)));
        }
        if (! is_array($configured)) {
            $configured = ['main_pump', 'drain'];
        }

        if (! $this->shouldRequireDrainBinding($zone)) {
            $configured = array_values(array_filter(
                $configured,
                static fn (mixed $binding): bool => is_string($binding) && trim($binding) !== 'drain'
            ));
        }

        return array_values(array_unique(array_merge($configured, $this->getCapabilityRequiredBindings($zone))));
    }

    /**
     * Получить обязательные роли по включённым capability зоны.
     */
    private function getCapabilityRequiredBindings(Zone $zone): array
    {
        $capabilities = is_array($zone->capabilities) ? $zone->capabilities : [];
        $required = [];

        if ($this->isCapabilityEnabled($capabilities['ph_control'] ?? false)) {
            $required = array_merge($required, self::PH_REQUIRED_BINDINGS);
        }

        if ($this->isCapabilityEnabled($capabilities['ec_control'] ?? false)) {
            $required = array_merge($required, self::EC_REQUIRED_BINDINGS);
        }

        return $required;
    }

    /**
     * Для 2-баковой схемы дренаж не обязателен.
     */
    private function shouldRequireDrainBinding(Zone $zone): bool
    {
        $profile = $this->resolveActiveAutomationProfile($zone);
        if (! $profile) {
            return true;
        }

        $subsystems = is_array($profile->subsystems) ? $profile->subsystems : [];
        if (empty($subsystems)) {
            return true;
        }

        $tanksCount = $this->extractIrrigationTanksCount($subsystems);
        if ($tanksCount === 2) {
            return false;
        }

        $topology = data_get($subsystems, 'diagnostics.execution.topology');
        if (is_string($topology) && str_contains(strtolower($topology), 'two_tank')) {
            return false;
        }

        return true;
    }

    private function resolveActiveAutomationProfile(Zone $zone): ?ZoneAutomationLogicProfile
    {
        if ($zone->relationLoaded('activeAutomationLogicProfile')) {
            $loaded = $zone->getRelation('activeAutomationLogicProfile');
            return $loaded instanceof ZoneAutomationLogicProfile ? $loaded : null;
        }

        return $zone->activeAutomationLogicProfile()->first();
    }

    private function extractIrrigationTanksCount(array $subsystems): ?int
    {
        $raw = data_get($subsystems, 'irrigation.execution.tanks_count');
        if (is_int($raw)) {
            return in_array($raw, [2, 3], true) ? $raw : null;
        }
        if (is_string($raw) && trim($raw) !== '') {
            $parsed = (int) trim($raw);
            return in_array($parsed, [2, 3], true) ? $parsed : null;
        }
        if (is_float($raw)) {
            $parsed = (int) round($raw);
            return in_array($parsed, [2, 3], true) ? $parsed : null;
        }

        return null;
    }

    /**
     * Проверить готовность зоны к запуску grow-cycle
     *
     * @return array [
     *               'ready' => bool,
     *               'warnings' => array,
     *               'errors' => array
     *               ]
     */
    public function checkZoneReadiness(Zone $zone): array
    {
        $warningDetails = [];
        $errorDetails = [];
        $optionalAssets = [
            'light' => false,
            'vent' => false,
            'heater' => false,
            'mist' => false,
        ];

        $nodesInfo = $this->checkOnlineNodes($zone);
        $hasNodes = $nodesInfo['total_count'] > 0;
        $hasOnlineNodes = $nodesInfo['online_count'] > 0;

        if (! $hasNodes) {
            $errorDetails[] = [
                'type' => 'no_nodes',
                'message' => 'Zone has no bound nodes',
            ];
        }

        if ($hasNodes && ! $hasOnlineNodes) {
            $errorDetails[] = [
                'type' => 'no_online_nodes',
                'message' => 'Zone has no online nodes',
            ];
        }

        // Проверка 1: Required bindings (только если strict_mode включен)
        $requiredBindings = $this->getRequiredBindings($zone);
        $requiredPidConfigTypes = $this->getRequiredPidConfigTypes($zone);
        $missingBindings = [];
        $calibrationRequiredBindings = array_values(array_intersect(
            $requiredBindings,
            array_merge(self::PH_REQUIRED_BINDINGS, self::EC_REQUIRED_BINDINGS)
        ));
        $missingCalibrations = [];
        $missingPidConfigTypes = [];
        if (! empty($requiredBindings)) {
            $missingBindings = $this->checkRequiredBindings($zone, $requiredBindings);
            if (! empty($missingBindings)) {
                $errorDetails[] = [
                    'type' => 'missing_bindings',
                    'message' => 'Required bindings are missing: '.implode(', ', $missingBindings),
                    'bindings' => $missingBindings,
                    'required' => $requiredBindings,
                ];
            }
        }

        if (! empty($calibrationRequiredBindings)) {
            $missingCalibrations = $this->checkRequiredCalibrations(
                $zone,
                array_values(array_diff($calibrationRequiredBindings, $missingBindings))
            );
            if (! empty($missingCalibrations)) {
                $errorDetails[] = [
                    'type' => 'missing_calibrations',
                    'message' => 'Required pump calibrations are missing: '.implode(', ', $missingCalibrations),
                    'bindings' => $missingCalibrations,
                    'required' => $calibrationRequiredBindings,
                ];
            }
        }

        if (! empty($requiredPidConfigTypes)) {
            $missingPidConfigTypes = $this->checkRequiredPidConfigs($zone, $requiredPidConfigTypes);
            if (! empty($missingPidConfigTypes)) {
                $errorDetails[] = [
                    'type' => 'missing_pid_configs',
                    'message' => 'Required zone PID configs are missing: '.implode(', ', $missingPidConfigTypes),
                    'pid_types' => $missingPidConfigTypes,
                    'required' => $requiredPidConfigTypes,
                ];
            }
        }

        $dispatchEnabled = $this->isGrowCycleStartDispatchEnabled();
        if (! $dispatchEnabled) {
            $errorDetails[] = [
                'type' => 'dispatch_disabled',
                'message' => 'Grow-cycle dispatch в automation-engine отключён runtime-флагом',
                'config_key' => 'automation_engine.grow_cycle_start_dispatch_enabled',
            ];
        }

        $blockingAlerts = $this->findHardBlockingAlerts($zone);
        if ($blockingAlerts !== []) {
            $errorDetails[] = [
                'type' => 'blocking_alerts',
                'message' => 'Есть активные блокирующие alerts automation-engine',
                'alerts' => $blockingAlerts,
            ];
        }

        // Проверка 2: Online nodes (warning only)
        if ($nodesInfo['offline_count'] > 0) {
            $warningDetails[] = [
                'type' => 'offline_nodes',
                'message' => "{$nodesInfo['offline_count']} node(s) are offline",
                'count' => $nodesInfo['offline_count'],
                'nodes' => $nodesInfo['nodes'],
            ];
        }

        $requiredAssets = [];
        foreach ($requiredBindings as $role) {
            $requiredAssets[$role] = ! in_array($role, $missingBindings, true);
        }

        $calibrationChecks = [];
        foreach ($calibrationRequiredBindings as $role) {
            if (in_array($role, $missingBindings, true)) {
                continue;
            }
            $calibrationChecks["{$role}_calibration"] = ! in_array($role, $missingCalibrations, true);
        }

        $pidConfigChecks = [];
        foreach ($requiredPidConfigTypes as $pidType) {
            $pidConfigChecks["pid_config_{$pidType}"] = ! in_array($pidType, $missingPidConfigTypes, true);
        }

        $checks = array_merge($requiredAssets, $calibrationChecks, [
            'has_nodes' => $hasNodes,
            'online_nodes' => $hasOnlineNodes,
            'dispatch_enabled' => $dispatchEnabled,
            'blocking_alerts_clear' => $blockingAlerts === [],
        ], $pidConfigChecks);

        $readiness = [
            'ready' => empty($errorDetails),
            'warnings' => [],
            'errors' => [],
            'warning_details' => $warningDetails,
            'error_details' => $errorDetails,
            'required_bindings' => $requiredBindings,
            'missing_bindings' => $missingBindings,
            'calibration_required_bindings' => $calibrationRequiredBindings,
            'missing_calibrations' => $missingCalibrations,
            'required_pid_config_types' => $requiredPidConfigTypes,
            'missing_pid_config_types' => $missingPidConfigTypes,
            'required_assets' => $requiredAssets,
            'optional_assets' => $optionalAssets,
            'nodes' => [
                'online' => $nodesInfo['online_count'],
                'total' => $nodesInfo['total_count'],
                'all_online' => $nodesInfo['offline_count'] === 0 && $nodesInfo['total_count'] > 0,
            ],
            'checks' => $checks,
            'dispatch_enabled' => $dispatchEnabled,
            'blocking_alerts' => $blockingAlerts,
        ];

        $readiness['warnings'] = $this->buildUserFacingWarnings($readiness);
        $readiness['errors'] = $this->buildUserFacingErrors($readiness);

        return $readiness;
    }

    /**
     * @param  array<string, mixed>  $readiness
     * @return array<int, string>
     */
    public function buildUserFacingErrors(array $readiness): array
    {
        $errors = [];
        $checks = is_array($readiness['checks'] ?? null) ? $readiness['checks'] : [];
        $hasNodes = (bool) ($checks['has_nodes'] ?? false);
        $hasOnlineNodes = (bool) ($checks['online_nodes'] ?? false);

        if (! $hasNodes) {
            $errors[] = 'Нет привязанных нод в зоне';
        }
        if ($hasNodes && ! $hasOnlineNodes) {
            $errors[] = 'Нет онлайн нод в зоне';
        }

        $roleMessages = [
            'main_pump' => 'Основная помпа не привязана к каналу',
            'drain' => 'Дренаж не привязан к каналу',
            'ph_acid_pump' => 'Насос pH кислоты не привязан к каналу',
            'ph_base_pump' => 'Насос pH щёлочи не привязан к каналу',
            'ec_npk_pump' => 'Насос EC NPK не привязан к каналу',
            'ec_calcium_pump' => 'Насос EC Calcium не привязан к каналу',
            'ec_magnesium_pump' => 'Насос EC Magnesium не привязан к каналу',
            'ec_micro_pump' => 'Насос EC Micro не привязан к каналу',
        ];
        $calibrationMessages = [
            'ph_acid_pump' => 'Для насоса pH кислоты не задана калибровка',
            'ph_base_pump' => 'Для насоса pH щёлочи не задана калибровка',
            'ec_npk_pump' => 'Для насоса EC NPK не задана калибровка',
            'ec_calcium_pump' => 'Для насоса EC Calcium не задана калибровка',
            'ec_magnesium_pump' => 'Для насоса EC Magnesium не задана калибровка',
            'ec_micro_pump' => 'Для насоса EC Micro не задана калибровка',
        ];
        $pidMessages = [
            'ph' => 'PID-настройки pH не сохранены для зоны',
            'ec' => 'PID-настройки EC не сохранены для зоны',
        ];

        foreach ($roleMessages as $role => $message) {
            if (array_key_exists($role, $checks) && ! $checks[$role]) {
                $errors[] = $message;
            }
        }
        foreach ($pidMessages as $pidType => $message) {
            $key = "pid_config_{$pidType}";
            if (array_key_exists($key, $checks) && ! $checks[$key]) {
                $errors[] = $message;
            }
        }

        $errorDetails = is_array($readiness['error_details'] ?? null) ? $readiness['error_details'] : [];
        foreach ($errorDetails as $issue) {
            if (! is_array($issue)) {
                continue;
            }

            $type = (string) ($issue['type'] ?? '');
            if ($type === 'dispatch_disabled') {
                $errors[] = 'Запуск в automation-engine отключён runtime-флагом';
                continue;
            }

            if ($type === 'blocking_alerts') {
                $alerts = is_array($issue['alerts'] ?? null) ? $issue['alerts'] : [];
                foreach ($alerts as $alert) {
                    if (! is_array($alert)) {
                        continue;
                    }

                    $code = (string) ($alert['code'] ?? '');
                    $errors[] = $this->blockingAlertMessage($code);
                }
                continue;
            }

            if (! in_array($type, ['missing_bindings', 'missing_calibrations', 'missing_pid_configs'], true)) {
                continue;
            }

            if ($type === 'missing_pid_configs') {
                $pidTypes = is_array($issue['pid_types'] ?? null) ? $issue['pid_types'] : [];
                foreach ($pidTypes as $pidType) {
                    if (! is_string($pidType) || $pidType === '') {
                        continue;
                    }

                    $errors[] = $pidMessages[$pidType] ?? "Не сохранён обязательный PID-конфиг: {$pidType}";
                }

                continue;
            }

            $bindings = is_array($issue['bindings'] ?? null) ? $issue['bindings'] : [];
            foreach ($bindings as $binding) {
                if (! is_string($binding) || $binding === '') {
                    continue;
                }

                if ($type === 'missing_calibrations' && isset($calibrationMessages[$binding])) {
                    $errors[] = $calibrationMessages[$binding];
                } elseif (isset($roleMessages[$binding])) {
                    $errors[] = $roleMessages[$binding];
                } else {
                    $errors[] = "Не привязан обязательный канал: {$binding}";
                }
            }
        }

        return array_values(array_unique($errors));
    }

    /**
     * @param  array<string, mixed>  $readiness
     * @return array<int, string>
     */
    public function buildUserFacingWarnings(array $readiness): array
    {
        $warnings = [];
        $warningDetails = is_array($readiness['warning_details'] ?? null) ? $readiness['warning_details'] : [];
        foreach ($warningDetails as $issue) {
            if (! is_array($issue)) {
                continue;
            }

            $type = (string) ($issue['type'] ?? '');
            if ($type === 'offline_nodes') {
                $count = (int) ($issue['count'] ?? 0);
                if ($count > 0) {
                    $warnings[] = $count === 1 ? '1 нода офлайн' : "{$count} нод офлайн";
                }
                continue;
            }

            $message = $issue['message'] ?? null;
            if (is_string($message) && $message !== '') {
                $warnings[] = $message;
            }
        }

        return array_values(array_unique($warnings));
    }

    /**
     * Legacy-совместимый метод для контроллеров инфраструктуры/команд.
     *
     * @return array{
     *   valid: bool,
     *   ready: bool,
     *   warnings: array<int, string>,
     *   errors: array<int, string>,
     *   details: array<string, mixed>
     * }
     */
    public function validate(int $zoneId): array
    {
        $zone = Zone::query()->find($zoneId);
        if (! $zone) {
            return [
                'valid' => false,
                'ready' => false,
                'warnings' => [],
                'errors' => ['Zone not found'],
                'details' => [],
            ];
        }

        $readiness = $this->checkZoneReadiness($zone);

        return [
            'valid' => $readiness['ready'],
            'ready' => $readiness['ready'],
            'warnings' => $this->buildUserFacingWarnings($readiness),
            'errors' => $this->buildUserFacingErrors($readiness),
            'details' => $readiness,
        ];
    }

    /**
     * Получить сводное состояние здоровья зоны для API.
     *
     * @return array{
     *   zone_id: int,
     *   ready: bool,
     *   warnings: array,
     *   errors: array,
     *   nodes_total: int,
     *   nodes_online: int,
     *   active_alerts_count: int
     * }
     */
    public function getZoneHealth(Zone $zone): array
    {
        $readiness = $this->checkZoneReadiness($zone);

        $nodes = $zone->nodes()
            ->select('id', 'status')
            ->get();

        $nodesTotal = $nodes->count();
        $nodesOnline = $nodes->filter(function ($node) {
            return is_string($node->status) && strtolower($node->status) === 'online';
        })->count();

        $activeAlertsCount = Alert::query()
            ->where('zone_id', $zone->id)
            ->where('status', 'ACTIVE')
            ->count();

        return [
            'zone_id' => $zone->id,
            'ready' => $readiness['ready'],
            'warnings' => $readiness['warnings'],
            'errors' => $readiness['errors'],
            'checks' => $readiness['checks'] ?? [],
            'error_details' => $readiness['error_details'] ?? [],
            'warning_details' => $readiness['warning_details'] ?? [],
            'dispatch_enabled' => (bool) ($readiness['dispatch_enabled'] ?? false),
            'blocking_alerts' => $readiness['blocking_alerts'] ?? [],
            'blocking_alerts_count' => count($readiness['blocking_alerts'] ?? []),
            'nodes_total' => $nodesTotal,
            'nodes_online' => $nodesOnline,
            'active_alerts_count' => $activeAlertsCount,
            'readiness' => $readiness,
        ];
    }

    private function isGrowCycleStartDispatchEnabled(): bool
    {
        return (bool) $this->runtimeConfig->automationEngineValue('grow_cycle_start_dispatch_enabled', false);
    }

    /**
     * @return array<int, array{id:int,code:string,status:string,severity:string|null,created_at:string|null,last_seen_at:string|null}>
     */
    private function findHardBlockingAlerts(Zone $zone): array
    {
        return Alert::query()
            ->where('zone_id', $zone->id)
            ->where('status', 'ACTIVE')
            ->whereIn('code', self::HARD_BLOCKING_ALERT_CODES)
            ->orderByDesc('created_at')
            ->get(['id', 'code', 'status', 'severity', 'created_at', 'last_seen_at'])
            ->map(static function (Alert $alert): array {
                return [
                    'id' => (int) $alert->id,
                    'code' => (string) $alert->code,
                    'status' => (string) $alert->status,
                    'severity' => is_string($alert->severity) ? $alert->severity : null,
                    'created_at' => $alert->created_at?->toIso8601String(),
                    'last_seen_at' => $alert->last_seen_at?->toIso8601String(),
                ];
            })
            ->values()
            ->all();
    }

    private function blockingAlertMessage(string $code): string
    {
        return match ($code) {
            'biz_zone_correction_config_missing' => 'Есть активный блокирующий alert: не настроен correction config зоны',
            'biz_zone_dosing_calibration_missing' => 'Есть активный блокирующий alert: не завершена калибровка дозирующих насосов',
            default => "Есть активный блокирующий alert: {$code}",
        };
    }

    /**
     * Проверить наличие required bindings
     *
     * @param  array  $requiredBindings  Список обязательных bindings
     * @return array Список отсутствующих bindings
     */
    private function checkRequiredBindings(Zone $zone, array $requiredBindings): array
    {
        // Если список пуст - ничего не проверяем
        if (empty($requiredBindings)) {
            return [];
        }

        if (! DB::getSchemaBuilder()->hasTable('channel_bindings')) {
            Log::error('channel_bindings table does not exist; readiness check is fail-closed', [
                'zone_id' => $zone->id,
                'required_bindings' => $requiredBindings,
            ]);
            return array_values($requiredBindings);
        }

        $existingBindings = ChannelBinding::query()
            ->whereIn('role', $requiredBindings)
            ->whereHas('infrastructureInstance', function ($query) use ($zone) {
                $query->where(function ($ownerQuery) use ($zone) {
                    $ownerQuery->where(function ($zoneOwner) use ($zone) {
                        $zoneOwner->where('owner_type', 'zone')
                            ->where('owner_id', $zone->id);
                    })->orWhere(function ($greenhouseOwner) use ($zone) {
                        $greenhouseOwner->where('owner_type', 'greenhouse')
                            ->where('owner_id', $zone->greenhouse_id);
                    });
                });
            })
            ->pluck('role')
            ->unique()
            ->toArray();

        $missingBindings = array_diff($requiredBindings, $existingBindings);

        return array_values($missingBindings);
    }

    /**
     * Проверить наличие активной calibration для обязательных dosing pumps.
     *
     * @param  array<int, string>  $requiredBindings
     * @return array<int, string>
     */
    private function checkRequiredCalibrations(Zone $zone, array $requiredBindings): array
    {
        if (empty($requiredBindings)) {
            return [];
        }

        $bindingsByRole = ChannelBinding::query()
            ->with('nodeChannel')
            ->whereIn('role', $requiredBindings)
            ->whereHas('infrastructureInstance', function ($query) use ($zone) {
                $query->where(function ($ownerQuery) use ($zone) {
                    $ownerQuery->where(function ($zoneOwner) use ($zone) {
                        $zoneOwner->where('owner_type', 'zone')
                            ->where('owner_id', $zone->id);
                    })->orWhere(function ($greenhouseOwner) use ($zone) {
                        $greenhouseOwner->where('owner_type', 'greenhouse')
                            ->where('owner_id', $zone->greenhouse_id);
                    });
                });
            })
            ->get()
            ->groupBy('role');

        $missing = [];
        foreach ($requiredBindings as $role) {
            $bindings = $bindingsByRole->get($role, collect());
            $hasCalibration = $bindings->contains(function (ChannelBinding $binding): bool {
                return $this->nodeChannelHasActiveCalibration($binding->nodeChannel);
            });

            if (! $hasCalibration) {
                $missing[] = $role;
            }
        }

        return array_values($missing);
    }

    /**
     * @return array<int, string>
     */
    private function getRequiredPidConfigTypes(Zone $zone): array
    {
        $env = env('APP_ENV', 'production');
        if (config('zones.readiness.e2e_mode', false) || $env === 'e2e') {
            return [];
        }

        if (! config('zones.readiness.strict_mode', true)) {
            return [];
        }

        return ['ph', 'ec'];
    }

    /**
     * @param  array<int, string>  $requiredTypes
     * @return array<int, string>
     */
    private function checkRequiredPidConfigs(Zone $zone, array $requiredTypes): array
    {
        if (empty($requiredTypes)) {
            return [];
        }

        if (! DB::getSchemaBuilder()->hasTable('zone_pid_configs')) {
            Log::error('zone_pid_configs table does not exist; readiness PID check is fail-closed', [
                'zone_id' => $zone->id,
                'required_pid_config_types' => $requiredTypes,
            ]);

            return array_values($requiredTypes);
        }

        $existingTypes = ZonePidConfig::query()
            ->where('zone_id', $zone->id)
            ->whereIn('type', $requiredTypes)
            ->get(['type', 'config'])
            ->filter(function (ZonePidConfig $config): bool {
                $payload = $config->config;

                return is_array($payload) && ! empty($payload) && ! array_is_list($payload);
            })
            ->pluck('type')
            ->unique()
            ->values()
            ->toArray();

        return array_values(array_diff($requiredTypes, $existingTypes));
    }

    private function nodeChannelHasActiveCalibration(?NodeChannel $channel): bool
    {
        if (! $channel) {
            return false;
        }

        $config = is_array($channel->config) ? $channel->config : [];
        $legacyMlPerSec = data_get($config, 'pump_calibration.ml_per_sec');
        if (is_numeric($legacyMlPerSec) && (float) $legacyMlPerSec > 0) {
            return true;
        }

        if (! DB::getSchemaBuilder()->hasTable('pump_calibrations')) {
            return false;
        }

        return DB::table('pump_calibrations')
            ->where('node_channel_id', $channel->id)
            ->where('is_active', true)
            ->where('ml_per_sec', '>', 0)
            ->where(function ($query) {
                $query->whereNull('valid_to')
                    ->orWhere('valid_to', '>', now());
            })
            ->exists();
    }

    /**
     * Проверить статус узлов (online/offline)
     *
     * @return array ['offline_count' => int, 'nodes' => array]
     */
    private function checkOnlineNodes(Zone $zone): array
    {
        $nodes = collect();
        $bindingsAvailable = DB::getSchemaBuilder()->hasTable('channel_bindings');

        if ($bindingsAvailable) {
            $nodes = ChannelBinding::query()
                ->join('node_channels', 'channel_bindings.node_channel_id', '=', 'node_channels.id')
                ->join('nodes', 'node_channels.node_id', '=', 'nodes.id')
                ->join('infrastructure_instances', 'channel_bindings.infrastructure_instance_id', '=', 'infrastructure_instances.id')
                ->where(function ($query) use ($zone) {
                    $query->where(function ($zoneOwner) use ($zone) {
                        $zoneOwner->where('infrastructure_instances.owner_type', 'zone')
                            ->where('infrastructure_instances.owner_id', $zone->id);
                    })->orWhere(function ($greenhouseOwner) use ($zone) {
                        $greenhouseOwner->where('infrastructure_instances.owner_type', 'greenhouse')
                            ->where('infrastructure_instances.owner_id', $zone->greenhouse_id);
                    });
                })
                ->select('nodes.id', 'nodes.uid', 'nodes.name', 'nodes.status')
                ->distinct()
                ->get();
        } else {
            Log::error('channel_bindings table does not exist; readiness node check will fallback to zone nodes', [
                'zone_id' => $zone->id,
            ]);
        }

        // Если bind-ы ещё не созданы (типичный onboarding), считаем ноды напрямую по zone_id.
        if ($nodes->isEmpty()) {
            $nodes = $zone->nodes()
                ->select('id', 'uid', 'name', 'status')
                ->get();
        }

        $onlineNodes = $nodes->filter(function ($node) {
            return is_string($node->status) && strtolower($node->status) === 'online';
        });

        $offlineNodes = $nodes->filter(function ($node) {
            return is_string($node->status) && strtolower($node->status) !== 'online';
        });

        return [
            'online_count' => $onlineNodes->count(),
            'offline_count' => $offlineNodes->count(),
            'total_count' => $nodes->count(),
            'nodes' => $offlineNodes->map(function ($node) {
                return [
                    'id' => $node->id,
                    'uid' => $node->uid,
                    'name' => $node->name,
                    'status' => $node->status,
                ];
            })->values()->toArray(),
        ];
    }

    /**
     * Нормализация capability-флага из bool/int/string.
     */
    private function isCapabilityEnabled(mixed $value): bool
    {
        if (is_bool($value)) {
            return $value;
        }

        if (is_int($value) || is_float($value)) {
            return (float) $value > 0;
        }

        if (is_string($value)) {
            return in_array(strtolower(trim($value)), ['1', 'true', 'yes', 'on'], true);
        }

        return false;
    }
}
