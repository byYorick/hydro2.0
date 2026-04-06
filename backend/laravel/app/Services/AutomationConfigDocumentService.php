<?php

namespace App\Services;

use App\Models\AutomationConfigDocument;
use App\Models\AutomationConfigVersion;
use App\Support\Automation\ZoneCorrectionResolvedConfigBuilder;
use App\Support\Automation\ZoneLogicProfileNormalizer;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class AutomationConfigDocumentService
{
    public function __construct(
        private readonly AutomationConfigRegistry $registry,
        private readonly ZoneLogicProfileNormalizer $logicProfileNormalizer,
        private readonly ZoneCorrectionResolvedConfigBuilder $zoneCorrectionResolvedConfigBuilder,
    ) {
    }

    public function getDocument(string $namespace, string $scopeType, int $scopeId, bool $materialize = true): ?AutomationConfigDocument
    {
        $document = AutomationConfigDocument::query()
            ->where('namespace', $namespace)
            ->where('scope_type', $scopeType)
            ->where('scope_id', $scopeId)
            ->first();

        if ($document || ! $materialize) {
            return $document;
        }

        return $this->materializeDefaultDocument($namespace, $scopeType, $scopeId);
    }

    /**
     * @return array<string, mixed>
     */
    public function getPayload(string $namespace, string $scopeType, int $scopeId, bool $materialize = true): array
    {
        $document = $this->getDocument($namespace, $scopeType, $scopeId, $materialize);
        $payload = $document?->payload;

        return is_array($payload) && (! array_is_list($payload) || $payload === [])
            ? $payload
            : $this->registry->defaultPayload($namespace);
    }

    /**
     * @return array<int, mixed>
     */
    public function getListPayload(string $namespace, string $scopeType, int $scopeId, bool $materialize = true): array
    {
        $document = $this->getDocument($namespace, $scopeType, $scopeId, $materialize);
        $payload = $document?->payload;

        return is_array($payload) && array_is_list($payload) ? $payload : [];
    }

    /**
     * @return array<string, mixed>
     */
    public function getSystemPayloadByLegacyNamespace(string $legacyNamespace, bool $materialize = true): array
    {
        $authorityNamespace = $this->registry->legacySystemNamespaceToAuthority($legacyNamespace);
        if (! is_string($authorityNamespace) || $authorityNamespace === '') {
            throw new \InvalidArgumentException("Unknown legacy system namespace {$legacyNamespace}.");
        }

        return $this->getPayload($authorityNamespace, AutomationConfigRegistry::SCOPE_SYSTEM, 0, $materialize);
    }

    public function upsertDocument(
        string $namespace,
        string $scopeType,
        int $scopeId,
        array $payload,
        ?int $userId = null,
        string $source = 'api'
    ): AutomationConfigDocument {
        $expectedScopeType = $this->registry->scopeType($namespace);
        if ($scopeType !== $expectedScopeType) {
            throw new \InvalidArgumentException("Namespace {$namespace} must be stored in scope {$expectedScopeType}.");
        }

        $currentDocument = AutomationConfigDocument::query()->where([
            'namespace' => $namespace,
            'scope_type' => $scopeType,
            'scope_id' => $scopeId,
        ])->first();
        $currentPayload = is_array($currentDocument?->payload) ? $currentDocument->payload : [];
        $normalizedPayload = $this->normalizePayload($namespace, $payload, $scopeType, $scopeId, $currentPayload);
        $this->registry->validate($namespace, $normalizedPayload);

        return DB::transaction(function () use ($namespace, $scopeType, $scopeId, $normalizedPayload, $userId, $source): AutomationConfigDocument {
            $document = $this->persistDocument($namespace, $scopeType, $scopeId, $normalizedPayload, $userId, $source);
            app(AutomationConfigCompiler::class)->compileAffectedScopes($scopeType, $scopeId);

            return $document->fresh();
        });
    }

    public function upsertRuntimeTuningBundle(
        int $zoneId,
        array $payload,
        ?int $userId = null,
        string $source = 'unified_api'
    ): AutomationConfigDocument {
        $namespace = AutomationConfigRegistry::NAMESPACE_ZONE_RUNTIME_TUNING_BUNDLE;
        $scopeType = AutomationConfigRegistry::SCOPE_ZONE;
        $currentDocument = AutomationConfigDocument::query()->where([
            'namespace' => $namespace,
            'scope_type' => $scopeType,
            'scope_id' => $zoneId,
        ])->first();
        $currentPayload = is_array($currentDocument?->payload) ? $currentDocument->payload : [];
        $normalizedPayload = $this->normalizePayload($namespace, $payload, $scopeType, $zoneId, $currentPayload);
        $this->registry->validate($namespace, $normalizedPayload);
        $resolvedTargets = $this->resolveRuntimeTuningBundleTargets($normalizedPayload);

        return DB::transaction(function () use ($zoneId, $normalizedPayload, $resolvedTargets, $userId, $source, $namespace, $scopeType): AutomationConfigDocument {
            $document = $this->persistDocument($namespace, $scopeType, $zoneId, $normalizedPayload, $userId, $source);

            foreach ($resolvedTargets['process_calibration'] as $mode => $modePayload) {
                $this->persistDocument(
                    $this->registry->processCalibrationNamespaceForMode($mode),
                    $scopeType,
                    $zoneId,
                    $modePayload,
                    $userId,
                    'runtime_tuning_bundle'
                );
            }

            foreach ($resolvedTargets['pid'] as $type => $pidPayload) {
                $this->persistDocument(
                    $this->registry->pidNamespace($type),
                    $scopeType,
                    $zoneId,
                    $pidPayload,
                    $userId,
                    'runtime_tuning_bundle'
                );
            }

            app(AutomationConfigCompiler::class)->compileZoneBundle($zoneId);
            $this->resolveZoneCorrectionBootstrapAlert($zoneId);

            return $document->fresh();
        });
    }

    public function ensureSystemDefaults(): void
    {
        foreach ($this->registry->requiredNamespacesForScope(AutomationConfigRegistry::SCOPE_SYSTEM) as $namespace) {
            $this->materializeDefaultDocument($namespace, AutomationConfigRegistry::SCOPE_SYSTEM, 0);
        }
        app(AutomationConfigCompiler::class)->compileSystemBundle();
    }

    public function ensureZoneDefaults(int $zoneId): void
    {
        foreach ($this->registry->requiredNamespacesForScope(AutomationConfigRegistry::SCOPE_ZONE) as $namespace) {
            $this->materializeDefaultDocument($namespace, AutomationConfigRegistry::SCOPE_ZONE, $zoneId);
        }

        app(AutomationConfigCompiler::class)->compileZoneBundle($zoneId);
        $this->resolveZoneCorrectionBootstrapAlert($zoneId);
    }

    /**
     * @param  array<string, array<string, mixed>>  $documentsByNamespace
     */
    public function upsertCycleDocuments(int $growCycleId, array $documentsByNamespace, ?int $userId = null): void
    {
        foreach ($documentsByNamespace as $namespace => $payload) {
            $this->upsertDocument($namespace, AutomationConfigRegistry::SCOPE_GROW_CYCLE, $growCycleId, $payload, $userId, 'cycle_start');
        }
    }

    public function ensureCycleDefaults(int $growCycleId): void
    {
        foreach ($this->registry->requiredNamespacesForScope(AutomationConfigRegistry::SCOPE_GROW_CYCLE) as $namespace) {
            $this->materializeDefaultDocument($namespace, AutomationConfigRegistry::SCOPE_GROW_CYCLE, $growCycleId);
        }
    }

    public function materializeDefaultDocument(string $namespace, string $scopeType, int $scopeId): AutomationConfigDocument
    {
        $document = AutomationConfigDocument::query()->firstOrNew([
            'namespace' => $namespace,
            'scope_type' => $scopeType,
            'scope_id' => $scopeId,
        ]);

        if ($document->exists) {
            return $document;
        }

        $payload = $this->normalizePayload($namespace, $this->registry->defaultPayload($namespace), $scopeType, $scopeId, []);
        $checksum = $this->checksum($payload);

        $document->schema_version = $this->registry->schemaVersion($namespace);
        $document->payload = $payload;
        $document->status = 'valid';
        $document->source = 'bootstrap';
        $document->checksum = $checksum;
        $document->updated_by = null;
        $document->save();

        AutomationConfigVersion::query()->create([
            'document_id' => $document->id,
            'namespace' => $namespace,
            'scope_type' => $scopeType,
            'scope_id' => $scopeId,
            'schema_version' => $document->schema_version,
            'payload' => $payload,
            'status' => 'valid',
            'source' => 'bootstrap',
            'checksum' => $checksum,
            'changed_by' => null,
            'changed_at' => now(),
        ]);

        return $document;
    }

    /**
     * @return array<string, mixed>
     */
    public function normalizePayload(
        string $namespace,
        array $payload,
        ?string $scopeType = null,
        ?int $scopeId = null,
        array $currentPayload = []
    ): array
    {
        if ($payload !== [] && array_is_list($payload) && $namespace !== AutomationConfigRegistry::NAMESPACE_CYCLE_MANUAL_OVERRIDES) {
            throw new \InvalidArgumentException("Payload for {$namespace} must be an object.");
        }

        return match ($namespace) {
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION => $this->normalizeZoneCorrectionPayload($payload),
            AutomationConfigRegistry::NAMESPACE_GREENHOUSE_LOGIC_PROFILE => $this->normalizeGreenhouseLogicProfilePayload($payload),
            AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE => $this->normalizeLogicProfilePayload(
                $payload,
                $scopeType === AutomationConfigRegistry::SCOPE_ZONE ? (int) $scopeId : 0,
                $currentPayload
            ),
            AutomationConfigRegistry::NAMESPACE_ZONE_RUNTIME_TUNING_BUNDLE => $this->normalizeRuntimeTuningBundlePayload($payload),
            default => $payload,
        };
    }

    /**
     * @return array<string, mixed>
     */
    private function normalizeZoneCorrectionPayload(array $payload): array
    {
        return [
            'preset_id' => isset($payload['preset_id']) ? (int) $payload['preset_id'] : null,
            'base_config' => is_array($payload['base_config'] ?? null) && ! array_is_list($payload['base_config'])
                ? $payload['base_config']
                : ZoneCorrectionConfigCatalog::defaults(),
            'phase_overrides' => is_array($payload['phase_overrides'] ?? null) && ! array_is_list($payload['phase_overrides'])
                ? $payload['phase_overrides']
                : [],
            'resolved_config' => $this->zoneCorrectionResolvedConfigBuilder->buildFromPayload($payload),
            'last_applied_at' => $payload['last_applied_at'] ?? null,
            'last_applied_version' => isset($payload['last_applied_version']) ? (int) $payload['last_applied_version'] : null,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function normalizeLogicProfilePayload(array $payload, int $zoneId, array $currentPayload = []): array
    {
        $profiles = is_array($payload['profiles'] ?? null) && ! array_is_list($payload['profiles'])
            ? $payload['profiles']
            : [];
        $normalizedProfiles = [];

        foreach ($profiles as $mode => $profile) {
            if (! is_string($mode) || ! is_array($profile) || array_is_list($profile)) {
                continue;
            }

            $profile = $this->mergeLegacyLogicProfileCompatibility($mode, $profile, $zoneId, $currentPayload);
            $normalizedProfiles[$mode] = $this->logicProfileNormalizer->normalizeProfile(
                $mode,
                $profile,
                'automation_logic_profile_document_normalized'
            );
        }

        $activeMode = isset($payload['active_mode']) && is_string($payload['active_mode'])
            ? $payload['active_mode']
            : null;

        return [
            'active_mode' => $activeMode,
            'profiles' => $normalizedProfiles,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function normalizeGreenhouseLogicProfilePayload(array $payload): array
    {
        $profiles = is_array($payload['profiles'] ?? null) && ! array_is_list($payload['profiles'])
            ? $payload['profiles']
            : [];
        $activeMode = isset($payload['active_mode']) && is_string($payload['active_mode'])
            ? $payload['active_mode']
            : null;
        $normalizedProfiles = [];

        foreach ($profiles as $mode => $profile) {
            if (! is_string($mode) || ! is_array($profile) || array_is_list($profile)) {
                continue;
            }

            $subsystems = is_array($profile['subsystems'] ?? null) && ! array_is_list($profile['subsystems'])
                ? $profile['subsystems']
                : [];
            $climate = is_array($subsystems['climate'] ?? null) && ! array_is_list($subsystems['climate'])
                ? $subsystems['climate']
                : ['enabled' => false];
            $execution = is_array($climate['execution'] ?? null) && ! array_is_list($climate['execution'])
                ? $climate['execution']
                : [];

            $normalizedProfiles[$mode] = [
                'mode' => $mode,
                'is_active' => $mode === $activeMode,
                'subsystems' => [
                    'climate' => [
                        'enabled' => (bool) ($climate['enabled'] ?? false),
                        'execution' => $execution,
                    ],
                ],
                'updated_at' => $profile['updated_at'] ?? null,
                'created_at' => $profile['created_at'] ?? null,
                'updated_by' => $profile['updated_by'] ?? null,
                'created_by' => $profile['created_by'] ?? null,
            ];
        }

        return [
            'active_mode' => $activeMode,
            'profiles' => $normalizedProfiles,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function normalizeRuntimeTuningBundlePayload(array $payload): array
    {
        $defaultPayload = $this->registry->defaultPayload(AutomationConfigRegistry::NAMESPACE_ZONE_RUNTIME_TUNING_BUNDLE);
        $presets = is_array($payload['presets'] ?? null) && array_is_list($payload['presets']) && $payload['presets'] !== []
            ? $payload['presets']
            : (is_array($defaultPayload['presets'] ?? null) ? $defaultPayload['presets'] : []);

        $selectedPresetKey = trim((string) ($payload['selected_preset_key'] ?? ''));
        if ($selectedPresetKey === '' && isset($presets[0]['key'])) {
            $selectedPresetKey = (string) $presets[0]['key'];
        }

        $advancedOverrides = is_array($payload['advanced_overrides'] ?? null) && ! array_is_list($payload['advanced_overrides'])
            ? $payload['advanced_overrides']
            : [];

        $resolvedTargets = $this->resolveRuntimeTuningBundleTargets([
            'selected_preset_key' => $selectedPresetKey,
            'presets' => $presets,
            'advanced_overrides' => $advancedOverrides,
        ]);

        return [
            'selected_preset_key' => $selectedPresetKey,
            'presets' => $presets,
            'advanced_overrides' => $advancedOverrides,
            'resolved_preview' => $resolvedTargets,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function mergeLegacyLogicProfileCompatibility(string $mode, array $profile, int $zoneId, array $currentPayload = []): array
    {
        $subsystems = is_array($profile['subsystems'] ?? null) && ! array_is_list($profile['subsystems'])
            ? $profile['subsystems']
            : [];
        $diagnostics = is_array($subsystems['diagnostics'] ?? null) && ! array_is_list($subsystems['diagnostics'])
            ? $subsystems['diagnostics']
            : [];
        $execution = is_array($diagnostics['execution'] ?? null) && ! array_is_list($diagnostics['execution'])
            ? $diagnostics['execution']
            : [];

        $currentExecution = data_get($currentPayload, "profiles.{$mode}.subsystems.diagnostics.execution");
        $currentExecution = is_array($currentExecution) && ! array_is_list($currentExecution) ? $currentExecution : [];

        $topology = strtolower(trim((string) ($execution['topology'] ?? $currentExecution['topology'] ?? '')));
        $isTwoTankTopology = str_contains($topology, 'two_tank');

        if ($isTwoTankTopology && ! array_key_exists('two_tank_commands', $execution)) {
            $existingCommands = data_get($currentExecution, 'two_tank_commands');
            $existingCommands = is_array($existingCommands) && ! array_is_list($existingCommands) ? $existingCommands : [];

            $execution['two_tank_commands'] = $existingCommands !== []
                ? $existingCommands
                : $this->defaultTwoTankCommandsFromAuthorityTemplates();
        }

        if ($isTwoTankTopology && ! array_key_exists('prepare_tolerance', $execution)) {
            $execution['prepare_tolerance'] = $this->resolveLegacyPrepareTolerance($zoneId, $currentExecution);
        }

        if ($execution !== []) {
            $diagnostics['execution'] = $execution;
        }
        if ($diagnostics !== []) {
            $subsystems['diagnostics'] = $diagnostics;
        }
        if ($subsystems !== []) {
            $profile['subsystems'] = $subsystems;
        }

        return $profile;
    }

    /**
     * @return array<string, mixed>
     */
    private function resolveLegacyPrepareTolerance(int $zoneId, array $currentExecution): array
    {
        $defaults = data_get(ZoneCorrectionConfigCatalog::defaults(), 'tolerance.prepare_tolerance');
        $defaults = is_array($defaults) && ! array_is_list($defaults) ? $defaults : ['ph_pct' => 5.0, 'ec_pct' => 10.0];

        if ($zoneId > 0) {
            $correctionPayload = $this->getPayload(
                AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
                AutomationConfigRegistry::SCOPE_ZONE,
                $zoneId,
                true
            );
            $resolvedConfig = is_array($correctionPayload['resolved_config'] ?? null) ? $correctionPayload['resolved_config'] : [];

            $irrigationTolerance = data_get($resolvedConfig, 'phases.irrigation.tolerance.prepare_tolerance');
            if (is_array($irrigationTolerance) && ! array_is_list($irrigationTolerance)) {
                return $irrigationTolerance;
            }

            $baseTolerance = data_get($resolvedConfig, 'base.tolerance.prepare_tolerance');
            if (is_array($baseTolerance) && ! array_is_list($baseTolerance)) {
                return $baseTolerance;
            }
        }

        $legacyTolerance = data_get($currentExecution, 'prepare_tolerance');
        if (is_array($legacyTolerance) && ! array_is_list($legacyTolerance)) {
            return $legacyTolerance;
        }

        return $defaults;
    }

    /**
     * @return array<string, mixed>
     */
    private function defaultTwoTankCommandsFromAuthorityTemplates(): array
    {
        $templates = $this->getPayload(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_COMMAND_TEMPLATES,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            true
        );

        $plans = [
            'irrigation_start',
            'irrigation_stop',
            'clean_fill_start',
            'clean_fill_stop',
            'solution_fill_start',
            'solution_fill_stop',
            'prepare_recirculation_start',
            'prepare_recirculation_stop',
            'irrigation_recovery_start',
            'irrigation_recovery_stop',
        ];

        $commands = [];
        foreach ($plans as $plan) {
            $steps = $templates[$plan] ?? [];
            $commands[$plan] = is_array($steps) && array_is_list($steps) ? $steps : [];
        }

        return $commands;
    }

    /**
     * @param  array<string, mixed>  $bundlePayload
     * @return array{
     *   process_calibration: array<string, array<string, mixed>>,
     *   pid: array<string, array<string, mixed>>
     * }
     */
    private function resolveRuntimeTuningBundleTargets(array $bundlePayload): array
    {
        $presets = is_array($bundlePayload['presets'] ?? null) && array_is_list($bundlePayload['presets'])
            ? $bundlePayload['presets']
            : [];
        $selectedPresetKey = (string) ($bundlePayload['selected_preset_key'] ?? '');
        $selectedPreset = collect($presets)->first(function (mixed $preset) use ($selectedPresetKey): bool {
            return is_array($preset) && (string) ($preset['key'] ?? '') === $selectedPresetKey;
        });
        $selectedPreset = is_array($selectedPreset) ? $selectedPreset : (is_array($presets[0] ?? null) ? $presets[0] : []);
        $advancedOverrides = is_array($bundlePayload['advanced_overrides'] ?? null) && ! array_is_list($bundlePayload['advanced_overrides'])
            ? $bundlePayload['advanced_overrides']
            : [];

        $baseProcessCalibration = is_array($selectedPreset['process_calibration'] ?? null) && ! array_is_list($selectedPreset['process_calibration'])
            ? $selectedPreset['process_calibration']
            : [];
        $basePid = is_array($selectedPreset['pid'] ?? null) && ! array_is_list($selectedPreset['pid'])
            ? $selectedPreset['pid']
            : [];
        $overrideProcessCalibration = is_array($advancedOverrides['process_calibration'] ?? null) && ! array_is_list($advancedOverrides['process_calibration'])
            ? $advancedOverrides['process_calibration']
            : [];
        $overridePid = is_array($advancedOverrides['pid'] ?? null) && ! array_is_list($advancedOverrides['pid'])
            ? $advancedOverrides['pid']
            : [];

        $resolvedProcessCalibration = [];
        foreach (['generic', 'solution_fill', 'tank_recirc', 'irrigation'] as $mode) {
            $basePayload = is_array($baseProcessCalibration[$mode] ?? null) ? $baseProcessCalibration[$mode] : [];
            $overridePayload = is_array($overrideProcessCalibration[$mode] ?? null) ? $overrideProcessCalibration[$mode] : [];
            $resolvedProcessCalibration[$mode] = $this->deepMerge($basePayload, $overridePayload);
        }

        $resolvedPid = [];
        foreach (['ph', 'ec'] as $type) {
            $basePayload = is_array($basePid[$type] ?? null) ? $basePid[$type] : [];
            $overridePayload = is_array($overridePid[$type] ?? null) ? $overridePid[$type] : [];
            $resolvedPid[$type] = $this->deepMerge($basePayload, $overridePayload);
        }

        return [
            'process_calibration' => $resolvedProcessCalibration,
            'pid' => $resolvedPid,
        ];
    }

    /**
     * @param  array<string, mixed>  $base
     * @param  array<string, mixed>  $override
     * @return array<string, mixed>
     */
    private function deepMerge(array $base, array $override): array
    {
        $result = $base;

        foreach ($override as $key => $value) {
            if (
                isset($result[$key])
                && is_array($result[$key])
                && ! array_is_list($result[$key])
                && is_array($value)
                && ! array_is_list($value)
            ) {
                $result[$key] = $this->deepMerge($result[$key], $value);
                continue;
            }

            $result[$key] = $value;
        }

        return $result;
    }

    private function persistDocument(
        string $namespace,
        string $scopeType,
        int $scopeId,
        array $normalizedPayload,
        ?int $userId,
        string $source
    ): AutomationConfigDocument {
        $checksum = $this->checksum($normalizedPayload);
        $document = AutomationConfigDocument::query()->firstOrNew([
            'namespace' => $namespace,
            'scope_type' => $scopeType,
            'scope_id' => $scopeId,
        ]);

        $document->schema_version = $this->registry->schemaVersion($namespace);
        $document->payload = $normalizedPayload;
        $document->status = 'valid';
        $document->source = $source;
        $document->checksum = $checksum;
        $document->updated_by = $userId;
        $document->save();

        AutomationConfigVersion::query()->create([
            'document_id' => $document->id,
            'namespace' => $namespace,
            'scope_type' => $scopeType,
            'scope_id' => $scopeId,
            'schema_version' => $document->schema_version,
            'payload' => $normalizedPayload,
            'status' => 'valid',
            'source' => $source,
            'checksum' => $checksum,
            'changed_by' => $userId,
            'changed_at' => now(),
        ]);

        return $document;
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    public function checksum(array $payload): string
    {
        return sha1(json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
    }

    private function resolveZoneCorrectionBootstrapAlert(int $zoneId): void
    {
        if ($zoneId <= 0 || ! Schema::hasTable('alerts')) {
            return;
        }

        app(AlertService::class)->resolveByCode($zoneId, 'biz_zone_correction_config_missing', [
            'resolved_by' => 'zone_correction_bootstrap',
            'resolved_via' => 'auto',
            'reason' => 'correction_config_bootstrap_defaults_applied',
        ]);
    }
}
