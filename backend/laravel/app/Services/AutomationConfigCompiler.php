<?php

namespace App\Services;

use App\Models\AutomationConfigDocument;
use App\Models\AutomationConfigViolation;
use App\Models\AutomationEffectiveBundle;
use App\Models\GrowCycle;
use App\Models\Zone;
use App\Support\Automation\RecipeNutritionRuntimeConfigResolver;
use App\Support\Automation\ZoneCorrectionResolvedConfigBuilder;
use Illuminate\Support\Facades\DB;

class AutomationConfigCompiler
{
    public function __construct(
        private readonly AutomationConfigRegistry $registry,
        private readonly ZoneCorrectionResolvedConfigBuilder $zoneCorrectionResolvedConfigBuilder,
        private readonly RecipeNutritionRuntimeConfigResolver $recipeNutritionRuntimeConfigResolver,
    ) {}

    public function compileAffectedScopes(string $scopeType, int $scopeId): void
    {
        match ($scopeType) {
            AutomationConfigRegistry::SCOPE_SYSTEM => $this->compileSystemCascade(),
            AutomationConfigRegistry::SCOPE_ZONE => $this->compileZoneCascade($scopeId),
            AutomationConfigRegistry::SCOPE_GROW_CYCLE => $this->compileGrowCycleBundle($scopeId),
            default => null,
        };
    }

    public function compileSystemCascade(): void
    {
        $this->compileSystemBundle();

        $zoneIds = Zone::query()->pluck('id')->all();
        foreach ($zoneIds as $zoneId) {
            $this->compileZoneBundle((int) $zoneId);
        }

        $cycleIds = GrowCycle::query()->active()->pluck('id')->all();
        foreach ($cycleIds as $cycleId) {
            $this->compileGrowCycleBundle((int) $cycleId);
        }
    }

    public function compileZoneCascade(int $zoneId): void
    {
        $this->compileZoneBundle($zoneId);

        $cycleIds = GrowCycle::query()
            ->where('zone_id', $zoneId)
            ->active()
            ->pluck('id')
            ->all();

        foreach ($cycleIds as $cycleId) {
            $this->compileGrowCycleBundle((int) $cycleId);
        }
    }

    public function compileSystemBundle(): AutomationEffectiveBundle
    {
        $systemConfig = [
            'runtime' => $this->payload(AutomationConfigRegistry::NAMESPACE_SYSTEM_RUNTIME, AutomationConfigRegistry::SCOPE_SYSTEM, 0),
            'automation_defaults' => $this->payload(AutomationConfigRegistry::NAMESPACE_SYSTEM_AUTOMATION_DEFAULTS, AutomationConfigRegistry::SCOPE_SYSTEM, 0),
            'command_templates' => $this->payload(AutomationConfigRegistry::NAMESPACE_SYSTEM_COMMAND_TEMPLATES, AutomationConfigRegistry::SCOPE_SYSTEM, 0),
            'process_calibration_defaults' => $this->payload(AutomationConfigRegistry::NAMESPACE_SYSTEM_PROCESS_CALIBRATION_DEFAULTS, AutomationConfigRegistry::SCOPE_SYSTEM, 0),
            'pump_calibration_policy' => $this->payload(AutomationConfigRegistry::NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY, AutomationConfigRegistry::SCOPE_SYSTEM, 0),
            'sensor_calibration_policy' => $this->payload(AutomationConfigRegistry::NAMESPACE_SYSTEM_SENSOR_CALIBRATION_POLICY, AutomationConfigRegistry::SCOPE_SYSTEM, 0),
            'alert_policies' => $this->payload(AutomationConfigRegistry::NAMESPACE_SYSTEM_ALERT_POLICIES, AutomationConfigRegistry::SCOPE_SYSTEM, 0),
        ];

        return $this->storeBundle(AutomationConfigRegistry::SCOPE_SYSTEM, 0, [
            'schema_version' => 1,
            'system' => $systemConfig,
        ]);
    }

    public function compileZoneBundle(int $zoneId): AutomationEffectiveBundle
    {
        $systemBundle = $this->bundleConfig(AutomationConfigRegistry::SCOPE_SYSTEM, 0);
        $logicProfile = $this->payload(AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE, AutomationConfigRegistry::SCOPE_ZONE, $zoneId);
        $activeMode = is_string($logicProfile['active_mode'] ?? null) ? $logicProfile['active_mode'] : null;
        $activeProfile = $activeMode !== null && is_array(data_get($logicProfile, "profiles.{$activeMode}"))
            ? data_get($logicProfile, "profiles.{$activeMode}")
            : null;

        return $this->storeBundle(AutomationConfigRegistry::SCOPE_ZONE, $zoneId, [
            'schema_version' => 1,
            'system' => $systemBundle['system'] ?? [],
            'zone' => [
                'logic_profile' => [
                    'active_mode' => $activeMode,
                    'active_profile' => $activeProfile,
                    'profiles' => $logicProfile['profiles'] ?? [],
                ],
                'correction' => $this->zoneCorrectionPayload($zoneId),
                'pid' => [
                    'ph' => [
                        'config' => $this->zonePidPayload(AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH, $zoneId),
                    ],
                    'ec' => [
                        'config' => $this->zonePidPayload(AutomationConfigRegistry::NAMESPACE_ZONE_PID_EC, $zoneId),
                    ],
                ],
                'process_calibration' => [
                    'generic' => $this->payload(AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_GENERIC, AutomationConfigRegistry::SCOPE_ZONE, $zoneId),
                    'solution_fill' => $this->payload(AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_SOLUTION_FILL, AutomationConfigRegistry::SCOPE_ZONE, $zoneId),
                    'tank_recirc' => $this->payload(AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_TANK_RECIRC, AutomationConfigRegistry::SCOPE_ZONE, $zoneId),
                    'irrigation' => $this->payload(AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_IRRIGATION, AutomationConfigRegistry::SCOPE_ZONE, $zoneId),
                ],
            ],
        ]);
    }

    public function compileGrowCycleBundle(int $growCycleId): AutomationEffectiveBundle
    {
        $cycle = GrowCycle::query()
            ->with('currentPhase')
            ->findOrFail($growCycleId);
        $zoneBundle = $this->bundleConfig(AutomationConfigRegistry::SCOPE_ZONE, (int) $cycle->zone_id);
        $zoneConfig = is_array($zoneBundle['zone'] ?? null) && ! array_is_list($zoneBundle['zone'])
            ? $zoneBundle['zone']
            : [];
        $zoneConfig['correction'] = $this->zoneCorrectionPayload(
            (int) $cycle->zone_id,
            $this->growCycleNutritionPayload($cycle)
        );

        $bundle = $this->storeBundle(AutomationConfigRegistry::SCOPE_GROW_CYCLE, $growCycleId, [
            'schema_version' => 1,
            'system' => $zoneBundle['system'] ?? [],
            'zone' => $zoneConfig,
            'cycle' => [
                'start_snapshot' => $this->payload(AutomationConfigRegistry::NAMESPACE_CYCLE_START_SNAPSHOT, AutomationConfigRegistry::SCOPE_GROW_CYCLE, $growCycleId),
                'phase_overrides' => $this->payload(AutomationConfigRegistry::NAMESPACE_CYCLE_PHASE_OVERRIDES, AutomationConfigRegistry::SCOPE_GROW_CYCLE, $growCycleId),
                'manual_overrides' => $this->listPayload(AutomationConfigRegistry::NAMESPACE_CYCLE_MANUAL_OVERRIDES, AutomationConfigRegistry::SCOPE_GROW_CYCLE, $growCycleId),
            ],
        ]);

        $settings = is_array($cycle->settings) ? $cycle->settings : [];
        $settings['bundle_revision'] = $bundle->bundle_revision;
        $cycle->settings = $settings;
        $cycle->save();

        return $bundle;
    }

    /**
     * @param  array<string, mixed>  $baseConfig
     * @param  array<string, mixed>  $phaseOverrides
     * @return array<string, mixed>
     */
    public function resolveCorrectionConfig(array $baseConfig, array $phaseOverrides): array
    {
        $resolved = $this->zoneCorrectionResolvedConfigBuilder->build(
            preset: null,
            baseConfig: $baseConfig,
            phaseOverrides: $phaseOverrides,
        );
        $meta = is_array($resolved['meta'] ?? null) && ! array_is_list($resolved['meta'])
            ? $resolved['meta']
            : [];
        $meta['version'] = 1;
        $meta['phase_overrides'] = $phaseOverrides;
        $resolved['meta'] = $meta;

        ZoneCorrectionConfigCatalog::validateResolvedConfig($resolved);

        return $resolved;
    }

    /**
     * @param  array<string, mixed>  $config
     */
    private function storeBundle(string $scopeType, int $scopeId, array $config): AutomationEffectiveBundle
    {
        $violations = $this->buildViolations($scopeType, $scopeId, $config);
        $status = collect($violations)->contains(fn (array $violation): bool => (bool) ($violation['blocking'] ?? false))
            ? 'invalid'
            : 'valid';
        $serializedConfig = json_encode($config, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
        $serializedViolations = json_encode($violations, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
        $inputsChecksum = sha1($serializedConfig);
        $bundleRevision = sha1($serializedConfig.'|'.$serializedViolations);

        return DB::transaction(function () use ($scopeType, $scopeId, $config, $violations, $status, $inputsChecksum, $bundleRevision): AutomationEffectiveBundle {
            AutomationConfigViolation::query()
                ->where('scope_type', $scopeType)
                ->where('scope_id', $scopeId)
                ->delete();

            if ($violations !== []) {
                AutomationConfigViolation::query()->insert(array_map(
                    fn (array $violation): array => [
                        'scope_type' => $scopeType,
                        'scope_id' => $scopeId,
                        'namespace' => $violation['namespace'],
                        'path' => $violation['path'],
                        'code' => $violation['code'],
                        'severity' => $violation['severity'],
                        'blocking' => $violation['blocking'],
                        'message' => $violation['message'],
                        'detected_at' => now(),
                    ],
                    $violations
                ));
            }

            AutomationEffectiveBundle::query()->updateOrCreate(
                [
                    'scope_type' => $scopeType,
                    'scope_id' => $scopeId,
                ],
                [
                    'bundle_revision' => $bundleRevision,
                    'schema_revision' => '1',
                    'config' => $config,
                    'violations' => $violations,
                    'status' => $status,
                    'compiled_at' => now(),
                    'inputs_checksum' => $inputsChecksum,
                ]
            );

            return AutomationEffectiveBundle::query()
                ->where('scope_type', $scopeType)
                ->where('scope_id', $scopeId)
                ->firstOrFail();
        });
    }

    /**
     * @param  array<string, mixed>  $config
     * @return array<int, array<string, mixed>>
     */
    private function buildViolations(string $scopeType, int $scopeId, array $config): array
    {
        $violations = [];

        if ($scopeType === AutomationConfigRegistry::SCOPE_ZONE) {
            $activeMode = data_get($config, 'zone.logic_profile.active_mode');
            if (! is_string($activeMode) || trim($activeMode) === '') {
                $violations[] = $this->violation(
                    AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
                    'active_mode',
                    'missing_active_logic_profile',
                    'error',
                    true,
                    "Zone {$scopeId} has no active automation logic profile"
                );
            }
        }

        if ($scopeType === AutomationConfigRegistry::SCOPE_GROW_CYCLE) {
            $startSnapshot = data_get($config, 'cycle.start_snapshot');
            if (! is_array($startSnapshot) || (array_is_list($startSnapshot) && $startSnapshot !== [])) {
                $violations[] = $this->violation(
                    AutomationConfigRegistry::NAMESPACE_CYCLE_START_SNAPSHOT,
                    '',
                    'missing_cycle_start_snapshot',
                    'error',
                    true,
                    "Grow cycle {$scopeId} has no cycle.start_snapshot document"
                );
            }
        }

        return $violations;
    }

    /**
     * @return array<string, mixed>
     */
    private function zoneCorrectionPayload(int $zoneId, ?array $nutrition = null): array
    {
        $payload = $this->payload(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zoneId
        );
        $resolvedConfig = is_array($payload['resolved_config'] ?? null) && ! array_is_list($payload['resolved_config'])
            ? $payload['resolved_config']
            : [];
        $meta = is_array($resolvedConfig['meta'] ?? null) && ! array_is_list($resolvedConfig['meta'])
            ? $resolvedConfig['meta']
            : [];

        $meta['version'] = $this->documentVersion(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zoneId
        );

        if (is_array($payload['phase_overrides'] ?? null) && ! array_is_list($payload['phase_overrides'])) {
            $meta['phase_overrides'] = $payload['phase_overrides'];
        }

        $resolvedConfig['meta'] = $meta;
        $resolvedConfig = $this->recipeNutritionRuntimeConfigResolver->applyToResolvedConfig($resolvedConfig, $nutrition);
        $payload['resolved_config'] = $resolvedConfig;

        return $payload;
    }

    /**
     * @return array<string, mixed>|null
     */
    private function growCycleNutritionPayload(GrowCycle $cycle): ?array
    {
        $phase = $cycle->currentPhase;
        if ($phase === null) {
            return null;
        }

        $mode = trim((string) ($phase->nutrient_mode ?? ''));
        if ($mode === '') {
            return null;
        }

        $result = [
            'mode' => $mode,
            'solution_volume_l' => $phase->nutrient_solution_volume_l,
            'components' => [
                'npk' => ['ratio_pct' => $phase->nutrient_npk_ratio_pct],
                'calcium' => ['ratio_pct' => $phase->nutrient_calcium_ratio_pct],
                'magnesium' => ['ratio_pct' => $phase->nutrient_magnesium_ratio_pct],
                'micro' => ['ratio_pct' => $phase->nutrient_micro_ratio_pct],
            ],
        ];

        $ecDosingMode = trim((string) ($phase->nutrient_ec_dosing_mode ?? ''));
        if ($ecDosingMode !== '') {
            $result['ec_dosing_mode'] = $ecDosingMode;
        }

        $irrigationSystemType = trim((string) ($phase->irrigation_system_type ?? ''));
        if ($irrigationSystemType !== '') {
            $result['irrigation_system_type'] = $irrigationSystemType;
        }
        $substrateType = trim((string) ($phase->substrate_type ?? ''));
        if ($substrateType !== '') {
            $result['substrate_type'] = $substrateType;
        }

        return $result;
    }

    private function documentVersion(string $namespace, string $scopeType, int $scopeId): int
    {
        return (int) AutomationConfigDocument::query()
            ->where('namespace', $namespace)
            ->where('scope_type', $scopeType)
            ->where('scope_id', $scopeId)
            ->withCount('versions')
            ->value('versions_count');
    }

    /**
     * @return array<string, mixed>
     */
    private function bundleConfig(string $scopeType, int $scopeId): array
    {
        $bundle = AutomationEffectiveBundle::query()
            ->where('scope_type', $scopeType)
            ->where('scope_id', $scopeId)
            ->first();

        $config = $bundle?->config;

        return is_array($config) && ! array_is_list($config) ? $config : [];
    }

    /**
     * @return array<string, mixed>
     */
    private function payload(string $namespace, string $scopeType, int $scopeId): array
    {
        $document = AutomationConfigDocument::query()
            ->where('namespace', $namespace)
            ->where('scope_type', $scopeType)
            ->where('scope_id', $scopeId)
            ->first();
        $payload = $document?->payload;

        return is_array($payload) && ! array_is_list($payload)
            ? $payload
            : app(AutomationConfigDocumentService::class)->getPayload($namespace, $scopeType, $scopeId, true);
    }

    private function zonePidPayload(string $namespace, int $zoneId): array
    {
        return $this->payload($namespace, AutomationConfigRegistry::SCOPE_ZONE, $zoneId);
    }

    /**
     * @return array<int, mixed>
     */
    private function listPayload(string $namespace, string $scopeType, int $scopeId): array
    {
        $document = AutomationConfigDocument::query()
            ->where('namespace', $namespace)
            ->where('scope_type', $scopeType)
            ->where('scope_id', $scopeId)
            ->first();
        $payload = $document?->payload;

        return is_array($payload) && array_is_list($payload) ? $payload : [];
    }

    /**
     * @return array<string, mixed>
     */
    private function violation(
        string $namespace,
        string $path,
        string $code,
        string $severity,
        bool $blocking,
        string $message
    ): array {
        return compact('namespace', 'path', 'code', 'severity', 'blocking', 'message');
    }
}
