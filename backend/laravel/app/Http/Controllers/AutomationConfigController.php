<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Jobs\PublishNodeConfigJob;
use App\Models\AutomationConfigVersion;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\GrowCycle;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Models\ChannelBinding;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigPresetService;
use App\Services\AutomationConfigRegistry;
use App\Services\AutomationRuntimeConfigService;
use App\Services\SystemAutomationSettingsCatalog;
use App\Services\ZoneConfigRevisionService;
use App\Services\ZoneCorrectionConfigCatalog;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class AutomationConfigController extends Controller
{
    public function __construct(
        private readonly AutomationConfigDocumentService $documents,
        private readonly AutomationConfigRegistry $registry,
        private readonly AutomationConfigPresetService $presets,
    ) {
    }

    public function show(Request $request, string $scopeType, int $scopeId, string $namespace): JsonResponse
    {
        try {
            $this->assertScopeMatchesNamespace($scopeType, $namespace);
            $this->authorizeScopeAccess($request, $scopeType, $scopeId, $namespace, false);
            $document = $this->documents->getDocument(
                $namespace,
                $scopeType,
                $scopeId,
                true
            );

            return response()->json([
                'status' => 'ok',
                'data' => $this->serializeDocument(
                    $namespace,
                    $scopeType,
                    $scopeId,
                    $document?->id,
                    $document?->payload ?? [],
                    $document?->status ?? 'valid',
                    $document?->updated_at?->toIso8601String(),
                    $document?->updated_by
                ),
            ]);
        } catch (\InvalidArgumentException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function update(Request $request, string $scopeType, int $scopeId, string $namespace): JsonResponse
    {
        try {
            $this->assertScopeMatchesNamespace($scopeType, $namespace);
            $this->authorizeScopeAccess($request, $scopeType, $scopeId, $namespace, true);
            $payload = $request->input('payload');
            if (! is_array($payload)) {
                throw new \InvalidArgumentException('payload must be an array/object.');
            }

            if ($namespace === AutomationConfigRegistry::NAMESPACE_SYSTEM_RUNTIME) {
                app(AutomationRuntimeConfigService::class)->applyOverrides($payload, $request->user()?->id);
                $document = $this->documents->getDocument($namespace, $scopeType, $scopeId, true);

                return response()->json([
                    'status' => 'ok',
                    'data' => $this->serializeDocument(
                        $namespace,
                        $scopeType,
                        $scopeId,
                        $document?->id,
                        is_array($document?->payload) ? $document->payload : [],
                        (string) ($document?->status ?? 'valid'),
                        $document?->updated_at?->toIso8601String(),
                        $document?->updated_by
                    ),
                ]);
            }

            $previousDocument = $this->documents->getDocument($namespace, $scopeType, $scopeId, false);
            $previousPayload = is_array($previousDocument?->payload) ? $previousDocument->payload : [];
            $document = $namespace === AutomationConfigRegistry::NAMESPACE_ZONE_RUNTIME_TUNING_BUNDLE
                ? $this->documents->upsertRuntimeTuningBundle($scopeId, $payload, $request->user()?->id, 'unified_api')
                : $this->documents->upsertDocument(
                    $namespace,
                    $scopeType,
                    $scopeId,
                    $payload,
                    $request->user()?->id,
                    'unified_api'
                );
            $this->emitZoneScopedEvent(
                $namespace,
                $scopeType,
                $scopeId,
                $previousPayload,
                is_array($document->payload) ? $document->payload : [],
                $request->user()?->id
            );
            $this->republishAffectedNodeConfigs($namespace, $scopeType, $scopeId);

            // Phase 5: bump zones.config_revision + write audit row, чтобы AE3
            // `_checkpoint()` увидел advance и в live-режиме подхватил свежий bundle.
            if ($scopeType === 'zone') {
                app(ZoneConfigRevisionService::class)->bumpAndAudit(
                    scopeType: $scopeType,
                    scopeId: $scopeId,
                    namespace: $namespace,
                    diff: ['previous_keys' => array_keys($previousPayload)],
                    userId: $request->user()?->id,
                    reason: 'config update via unified API',
                );
            }

            return response()->json([
                'status' => 'ok',
                'data' => $this->serializeDocument(
                    $namespace,
                    $scopeType,
                    $scopeId,
                    $document->id,
                    is_array($document->payload) ? $document->payload : [],
                    (string) $document->status,
                    $document->updated_at?->toIso8601String(),
                    $document->updated_by
                ),
            ]);
        } catch (\InvalidArgumentException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function history(Request $request, string $scopeType, int $scopeId, string $namespace): JsonResponse
    {
        try {
            $this->assertScopeMatchesNamespace($scopeType, $namespace);
            $this->authorizeScopeAccess($request, $scopeType, $scopeId, $namespace, false);

            $versions = AutomationConfigVersion::query()
                ->where('scope_type', $scopeType)
                ->where('scope_id', $scopeId)
                ->where('namespace', $namespace)
                ->orderByDesc('id')
                ->get()
                ->values();

            return response()->json([
                'status' => 'ok',
                'data' => $versions->map(function (AutomationConfigVersion $version, int $index) use ($versions, $namespace) {
                    return $this->serializeVersion(
                        $namespace,
                        $version,
                        $versions->count() - $index
                    );
                })->all(),
            ]);
        } catch (\InvalidArgumentException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function showRevision(
        Request $request,
        string $scopeType,
        int $scopeId,
        string $namespace,
        int $version,
    ): JsonResponse {
        try {
            $this->assertScopeMatchesNamespace($scopeType, $namespace);
            $this->authorizeScopeAccess($request, $scopeType, $scopeId, $namespace, false);

            $row = $this->findRevisionBySequence($scopeType, $scopeId, $namespace, $version);
            if ($row === null) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'REVISION_NOT_FOUND',
                    'message' => "Revision {$version} not found",
                ], Response::HTTP_NOT_FOUND);
            }

            return response()->json([
                'status' => 'ok',
                'data' => $this->serializeVersion($namespace, $row['version'], $row['sequence']),
            ]);
        } catch (\InvalidArgumentException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function restoreRevision(
        Request $request,
        string $scopeType,
        int $scopeId,
        string $namespace,
        int $version,
    ): JsonResponse {
        try {
            $this->assertScopeMatchesNamespace($scopeType, $namespace);
            $this->authorizeScopeAccess($request, $scopeType, $scopeId, $namespace, true);

            $row = $this->findRevisionBySequence($scopeType, $scopeId, $namespace, $version);
            if ($row === null) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'REVISION_NOT_FOUND',
                    'message' => "Revision {$version} not found",
                ], Response::HTTP_NOT_FOUND);
            }

            $snapshotPayload = is_array($row['version']->payload) ? $row['version']->payload : [];
            $previousDocument = $this->documents->getDocument($namespace, $scopeType, $scopeId, false);
            $previousPayload = is_array($previousDocument?->payload) ? $previousDocument->payload : [];

            $document = $this->documents->upsertDocument(
                $namespace,
                $scopeType,
                $scopeId,
                $snapshotPayload,
                $request->user()?->id,
                'authority_restore',
            );
            $this->emitZoneScopedEvent(
                $namespace,
                $scopeType,
                $scopeId,
                $previousPayload,
                is_array($document->payload) ? $document->payload : [],
                $request->user()?->id,
            );
            $this->republishAffectedNodeConfigs($namespace, $scopeType, $scopeId);

            if ($scopeType === 'zone') {
                app(ZoneConfigRevisionService::class)->bumpAndAudit(
                    scopeType: $scopeType,
                    scopeId: $scopeId,
                    namespace: $namespace,
                    diff: ['restored_from_version' => $version],
                    userId: $request->user()?->id,
                    reason: "restored revision v{$version}",
                );
            }

            return response()->json([
                'status' => 'ok',
                'data' => $this->serializeDocument(
                    $namespace,
                    $scopeType,
                    $scopeId,
                    $document->id,
                    is_array($document->payload) ? $document->payload : [],
                    (string) ($document->status ?? 'valid'),
                    $document->updated_at?->toIso8601String(),
                    $document->updated_by,
                ),
            ]);
        } catch (\InvalidArgumentException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    /**
     * @return array{version: AutomationConfigVersion, sequence: int}|null
     */
    private function findRevisionBySequence(
        string $scopeType,
        int $scopeId,
        string $namespace,
        int $sequence,
    ): ?array {
        $versions = AutomationConfigVersion::query()
            ->where('scope_type', $scopeType)
            ->where('scope_id', $scopeId)
            ->where('namespace', $namespace)
            ->orderByDesc('id')
            ->get()
            ->values();

        $total = $versions->count();
        if ($sequence < 1 || $sequence > $total) {
            return null;
        }

        // sequenceVersion = total - index (0-based desc listing → oldest = 1, newest = total)
        $index = $total - $sequence;
        $row = $versions->get($index);
        if (! $row) {
            return null;
        }

        return ['version' => $row, 'sequence' => $sequence];
    }

    public function destroy(Request $request, string $scopeType, int $scopeId, string $namespace): JsonResponse
    {
        try {
            $this->assertScopeMatchesNamespace($scopeType, $namespace);
            $this->authorizeScopeAccess($request, $scopeType, $scopeId, $namespace, true);

            if ($scopeType !== AutomationConfigRegistry::SCOPE_SYSTEM || $scopeId !== 0) {
                throw new \InvalidArgumentException('Reset is only supported for system authority documents.');
            }

            if ($namespace === AutomationConfigRegistry::NAMESPACE_SYSTEM_RUNTIME) {
                app(AutomationRuntimeConfigService::class)->resetOverrides();
                $document = $this->documents->getDocument($namespace, $scopeType, $scopeId, true);
            } else {
                $document = $this->documents->upsertDocument(
                    $namespace,
                    $scopeType,
                    $scopeId,
                    $this->registry->defaultPayload($namespace),
                    $request->user()?->id,
                    'authority_reset'
                );
            }

            return response()->json([
                'status' => 'ok',
                'data' => $this->serializeDocument(
                    $namespace,
                    $scopeType,
                    $scopeId,
                    $document?->id,
                    is_array($document?->payload) ? $document->payload : [],
                    (string) ($document?->status ?? 'valid'),
                    $document?->updated_at?->toIso8601String(),
                    $document?->updated_by
                ),
            ]);
        } catch (\InvalidArgumentException $exception) {
            return response()->json([
                'status' => 'error',
                'message' => $exception->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    /**
     * @param  array<string, mixed>  $previousPayload
     * @param  array<string, mixed>  $payload
     */
    private function emitZoneScopedEvent(
        string $namespace,
        string $scopeType,
        int $scopeId,
        array $previousPayload,
        array $payload,
        ?int $userId,
    ): void {
        if ($scopeType !== AutomationConfigRegistry::SCOPE_ZONE) {
            return;
        }

        $pidType = match ($namespace) {
            AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH => 'ph',
            AutomationConfigRegistry::NAMESPACE_ZONE_PID_EC => 'ec',
            default => null,
        };

        if ($pidType !== null) {
            ZoneEvent::query()->create([
                'zone_id' => $scopeId,
                'type' => 'PID_CONFIG_UPDATED',
                'payload_json' => [
                    'type' => $pidType,
                    'updated_by' => $userId,
                    'old_config' => $previousPayload,
                    'new_config' => $payload,
                ],
            ]);

            return;
        }

        $mode = match ($namespace) {
            AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_GENERIC => 'generic',
            AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_SOLUTION_FILL => 'solution_fill',
            AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_TANK_RECIRC => 'tank_recirc',
            AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_IRRIGATION => 'irrigation',
            default => null,
        };

        if ($mode === null) {
            return;
        }

        ZoneEvent::query()->create([
            'zone_id' => $scopeId,
            'type' => 'PROCESS_CALIBRATION_SAVED',
            'payload_json' => [
                'mode' => $mode,
                'source' => $payload['source'] ?? 'manual',
                'confidence' => $payload['confidence'] ?? null,
                'transport_delay_sec' => $payload['transport_delay_sec'] ?? null,
                'settle_sec' => $payload['settle_sec'] ?? null,
                'ec_gain_per_ml' => $payload['ec_gain_per_ml'] ?? null,
                'ph_up_gain_per_ml' => $payload['ph_up_gain_per_ml'] ?? null,
                'ph_down_gain_per_ml' => $payload['ph_down_gain_per_ml'] ?? null,
                'ph_per_ec_ml' => $payload['ph_per_ec_ml'] ?? null,
                'ec_per_ph_ml' => $payload['ec_per_ph_ml'] ?? null,
                'updated_by' => $userId,
                'previous' => $previousPayload !== [] ? [
                    'confidence' => $previousPayload['confidence'] ?? null,
                    'transport_delay_sec' => $previousPayload['transport_delay_sec'] ?? null,
                    'settle_sec' => $previousPayload['settle_sec'] ?? null,
                    'ec_gain_per_ml' => $previousPayload['ec_gain_per_ml'] ?? null,
                    'ph_up_gain_per_ml' => $previousPayload['ph_up_gain_per_ml'] ?? null,
                    'ph_down_gain_per_ml' => $previousPayload['ph_down_gain_per_ml'] ?? null,
                    'ph_per_ec_ml' => $previousPayload['ph_per_ec_ml'] ?? null,
                    'ec_per_ph_ml' => $previousPayload['ec_per_ph_ml'] ?? null,
                ] : null,
            ],
        ]);
    }

    private function assertScopeMatchesNamespace(string $scopeType, string $namespace): void
    {
        if (! in_array($scopeType, [
            AutomationConfigRegistry::SCOPE_SYSTEM,
            AutomationConfigRegistry::SCOPE_GREENHOUSE,
            AutomationConfigRegistry::SCOPE_ZONE,
            AutomationConfigRegistry::SCOPE_GROW_CYCLE,
        ], true)) {
            throw new \InvalidArgumentException("Unsupported scope type {$scopeType}.");
        }

        if ($this->registry->scopeType($namespace) !== $scopeType) {
            throw new \InvalidArgumentException("Namespace {$namespace} must be addressed in scope {$this->registry->scopeType($namespace)}.");
        }
    }

    /**
     * @param  array<string, mixed>  $payload
     * @return array<string, mixed>
     */
    private function serializeDocument(
        string $namespace,
        string $scopeType,
        int $scopeId,
        ?int $documentId,
        array $payload,
        string $status,
        ?string $updatedAt,
        ?int $updatedBy,
    ): array {
        $serialized = [
            'id' => $documentId,
            'namespace' => $namespace,
            'scope_type' => $scopeType,
            'scope_id' => $scopeId,
            'schema_version' => $this->registry->schemaVersion($namespace),
            'payload' => $payload,
            'status' => $status,
            'updated_at' => $updatedAt,
            'updated_by' => $updatedBy,
        ];

        if ($namespace === AutomationConfigRegistry::NAMESPACE_SYSTEM_RUNTIME) {
            $serialized['payload'] = app(AutomationRuntimeConfigService::class)->editableSettingsMap();
        }

        if ($namespace === AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION) {
            $serialized = array_merge($serialized, $this->serializeZoneCorrectionDocument($scopeId, $payload));
        }

        if ($namespace === AutomationConfigRegistry::NAMESPACE_SYSTEM_RUNTIME) {
            $serialized = array_merge($serialized, $this->serializeSystemRuntimeDocument());
        }

        $legacySystemNamespace = $this->registry->authorityToLegacySystemNamespace($namespace);
        if ($legacySystemNamespace !== null) {
            $serialized = array_merge($serialized, $this->serializeLegacySystemDocument($legacySystemNamespace));
        }

        if ($namespace === AutomationConfigRegistry::NAMESPACE_GREENHOUSE_LOGIC_PROFILE) {
            $serialized = array_merge($serialized, $this->serializeGreenhouseLogicProfileDocument($scopeId, $payload));
        }

        return $serialized;
    }

    /**
     * @param  array<string, mixed>  $payload
     * @return array<string, mixed>
     */
    private function serializeZoneCorrectionDocument(int $zoneId, array $payload): array
    {
        $presetId = isset($payload['preset_id']) ? (int) $payload['preset_id'] : null;
        $availablePresets = array_map(
            fn (array $preset) => $this->serializePreset($preset),
            $this->presets->list(AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION)
        );
        $selectedPreset = collect($availablePresets)->firstWhere('id', $presetId);
        $version = AutomationConfigVersion::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zoneId)
            ->where('namespace', AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION)
            ->count();

        return [
            'zone_id' => $zoneId,
            'preset' => $selectedPreset,
            'base_config' => is_array($payload['base_config'] ?? null) ? $payload['base_config'] : ZoneCorrectionConfigCatalog::defaults(),
            'phase_overrides' => is_array($payload['phase_overrides'] ?? null) ? $payload['phase_overrides'] : [],
            'resolved_config' => $this->normalizeZoneCorrectionResolvedConfig(
                is_array($payload['resolved_config'] ?? null) ? $payload['resolved_config'] : [
                    'base' => ZoneCorrectionConfigCatalog::defaults(),
                    'phases' => [],
                ],
                is_array($payload['phase_overrides'] ?? null) ? $payload['phase_overrides'] : [],
                $version,
            ),
            'version' => $version > 0 ? $version : null,
            'last_applied_at' => $payload['last_applied_at'] ?? null,
            'last_applied_version' => isset($payload['last_applied_version']) ? (int) $payload['last_applied_version'] : null,
            'meta' => [
                'phases' => ZoneCorrectionConfigCatalog::PHASES,
                'defaults' => ZoneCorrectionConfigCatalog::defaults(),
                'field_catalog' => ZoneCorrectionConfigCatalog::fieldCatalog(),
                'pump_calibration_field_catalog' => SystemAutomationSettingsCatalog::fieldCatalog('pump_calibration'),
            ],
            'available_presets' => $availablePresets,
        ];
    }

    /**
     * @param  array<string, mixed>  $resolvedConfig
     * @param  array<string, mixed>  $phaseOverrides
     * @return array<string, mixed>
     */
    private function normalizeZoneCorrectionResolvedConfig(array $resolvedConfig, array $phaseOverrides, int $version): array
    {
        if ($resolvedConfig === [] || array_is_list($resolvedConfig)) {
            $resolvedConfig = [
                'base' => ZoneCorrectionConfigCatalog::defaults(),
                'phases' => [],
            ];
        }

        $meta = is_array($resolvedConfig['meta'] ?? null) && ! array_is_list($resolvedConfig['meta'])
            ? $resolvedConfig['meta']
            : [];
        $meta['version'] = $version > 0 ? $version : null;
        $meta['phase_overrides'] = $phaseOverrides;
        $resolvedConfig['meta'] = $meta;

        return $resolvedConfig;
    }

    /**
     * @return array<string, mixed>
     */
    private function serializeVersion(string $namespace, AutomationConfigVersion $version, int $sequenceVersion): array
    {
        $payload = is_array($version->payload) ? $version->payload : [];

        if ($namespace === AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION) {
            $presetId = isset($payload['preset_id']) ? (int) $payload['preset_id'] : null;
            $selectedPreset = null;
            if ($presetId !== null) {
                try {
                    $preset = $this->presets->findOrFail($presetId, AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION);
                    $selectedPreset = $this->serializePreset($this->presets->serialize($preset));
                } catch (\Throwable) {
                    $selectedPreset = null;
                }
            }

            return [
                'id' => $version->id,
                'version' => $sequenceVersion,
                'change_type' => (string) $version->source,
                'preset' => $selectedPreset,
                'changed_by' => $version->changed_by,
                'changed_at' => $version->changed_at?->toIso8601String(),
                'base_config' => is_array($payload['base_config'] ?? null) ? $payload['base_config'] : [],
                'phase_overrides' => is_array($payload['phase_overrides'] ?? null) ? $payload['phase_overrides'] : [],
                'resolved_config' => is_array($payload['resolved_config'] ?? null) ? $payload['resolved_config'] : [
                    'base' => [],
                    'phases' => [],
                ],
            ];
        }

        return [
            'id' => $version->id,
            'version' => $sequenceVersion,
            'changed_by' => $version->changed_by,
            'changed_at' => $version->changed_at?->toIso8601String(),
            'payload' => $payload,
            'status' => $version->status,
            'source' => $version->source,
        ];
    }

    private function authorizeScopeAccess(
        Request $request,
        string $scopeType,
        int $scopeId,
        string $namespace,
        bool $writeAccess,
    ): void
    {
        $user = $request->user();
        if (! $user) {
            abort(401, 'Unauthorized');
        }

        if ($scopeType === AutomationConfigRegistry::SCOPE_SYSTEM) {
            $role = (string) ($user->role ?? 'viewer');

            if ($namespace === AutomationConfigRegistry::NAMESPACE_SYSTEM_RUNTIME) {
                if (! in_array($role, ['admin', 'operator', 'engineer', 'agronomist'], true)) {
                    abort(403, 'Forbidden: Access denied to runtime automation config');
                }

                return;
            }

            if ($writeAccess && ! $user->isAdmin()) {
                abort(403, 'Forbidden: Access denied to system automation config');
            }

            return;
        }

        if ($scopeType === AutomationConfigRegistry::SCOPE_GREENHOUSE) {
            $greenhouse = Greenhouse::query()->findOrFail($scopeId);
            if (! ZoneAccessHelper::canAccessGreenhouseScope($user, $greenhouse)) {
                abort(403, 'Forbidden: Access denied to this greenhouse');
            }

            return;
        }

        if ($scopeType === AutomationConfigRegistry::SCOPE_ZONE) {
            $zone = Zone::query()->findOrFail($scopeId);
            if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
                abort(403, 'Forbidden: Access denied to this zone');
            }

            return;
        }

        if ($scopeType === AutomationConfigRegistry::SCOPE_GROW_CYCLE) {
            $cycle = GrowCycle::query()->findOrFail($scopeId);
            $zone = Zone::query()->findOrFail((int) $cycle->zone_id);
            if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
                abort(403, 'Forbidden: Access denied to this grow cycle');
            }
        }
    }

    /**
     * @param  array<string, mixed>  $payload
     * @return array<string, mixed>
     */
    private function serializeGreenhouseLogicProfileDocument(int $greenhouseId, array $payload): array
    {
        return [
            'active_mode' => is_string($payload['active_mode'] ?? null) ? $payload['active_mode'] : null,
            'profiles' => is_array($payload['profiles'] ?? null) ? $payload['profiles'] : [],
            'bindings' => $this->greenhouseClimateBindings($greenhouseId),
            'storage_ready' => true,
        ];
    }

    /**
     * @return array{
     *   climate_sensors: array<int, int>,
     *   weather_station_sensors: array<int, int>,
     *   vent_actuators: array<int, int>,
     *   fan_actuators: array<int, int>
     * }
     */
    private function greenhouseClimateBindings(int $greenhouseId): array
    {
        $bindings = ChannelBinding::query()
            ->select(['channel_bindings.role', 'node_channels.node_id'])
            ->join('infrastructure_instances', 'infrastructure_instances.id', '=', 'channel_bindings.infrastructure_instance_id')
            ->join('node_channels', 'node_channels.id', '=', 'channel_bindings.node_channel_id')
            ->where('infrastructure_instances.owner_type', 'greenhouse')
            ->where('infrastructure_instances.owner_id', $greenhouseId)
            ->whereIn('channel_bindings.role', [
                'climate_sensor',
                'weather_station_sensor',
                'vent_actuator',
                'fan_actuator',
            ])
            ->get();

        return [
            'climate_sensors' => $this->bindingNodeIdsForRole($bindings->all(), 'climate_sensor'),
            'weather_station_sensors' => $this->bindingNodeIdsForRole($bindings->all(), 'weather_station_sensor'),
            'vent_actuators' => $this->bindingNodeIdsForRole($bindings->all(), 'vent_actuator'),
            'fan_actuators' => $this->bindingNodeIdsForRole($bindings->all(), 'fan_actuator'),
        ];
    }

    /**
     * @param  array<int, object>  $bindings
     * @return array<int, int>
     */
    private function bindingNodeIdsForRole(array $bindings, string $role): array
    {
        return collect($bindings)
            ->filter(static fn ($binding): bool => (string) ($binding->role ?? '') === $role)
            ->map(static fn ($binding): ?int => isset($binding->node_id) ? (int) $binding->node_id : null)
            ->filter(static fn (?int $nodeId): bool => is_int($nodeId) && $nodeId > 0)
            ->unique()
            ->values()
            ->all();
    }

    /**
     * @return array<string, mixed>
     */
    private function serializeSystemRuntimeDocument(): array
    {
        return [
            'snapshot' => app(AutomationRuntimeConfigService::class)->settingsSnapshot(),
            'meta' => [
                'defaults' => AutomationRuntimeConfigService::defaultSettingsMapStatic(),
                'field_catalog' => [],
            ],
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function serializeLegacySystemDocument(string $legacyNamespace): array
    {
        return [
            'meta' => [
                'defaults' => SystemAutomationSettingsCatalog::defaults($legacyNamespace),
                'field_catalog' => SystemAutomationSettingsCatalog::fieldCatalog($legacyNamespace),
            ],
        ];
    }

    /**
     * @param  array<string, mixed>  $preset
     * @return array<string, mixed>
     */
    private function serializePreset(array $preset): array
    {
        return [
            'id' => $preset['id'] ?? null,
            'namespace' => $preset['namespace'] ?? null,
            'scope' => $preset['scope'] ?? 'custom',
            'is_locked' => (bool) ($preset['is_locked'] ?? false),
            'is_active' => (bool) ($preset['is_active'] ?? false),
            'name' => $preset['name'] ?? 'Preset',
            'slug' => $preset['slug'] ?? null,
            'description' => $preset['description'] ?? null,
            'schema_version' => $preset['schema_version'] ?? 1,
            'config' => is_array($preset['payload'] ?? null) ? $preset['payload'] : [],
            'updated_by' => $preset['updated_by'] ?? null,
            'updated_at' => $preset['updated_at'] ?? null,
        ];
    }

    private function republishAffectedNodeConfigs(string $namespace, string $scopeType, int $scopeId): void
    {
        if ($scopeType !== AutomationConfigRegistry::SCOPE_ZONE || $namespace !== AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE) {
            return;
        }

        DeviceNode::query()
            ->where('zone_id', $scopeId)
            ->where('type', 'irrig')
            ->pluck('id')
            ->each(static fn (int $nodeId): mixed => PublishNodeConfigJob::dispatch($nodeId));
    }
}
