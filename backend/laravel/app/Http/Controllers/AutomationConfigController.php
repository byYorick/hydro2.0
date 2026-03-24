<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\AutomationConfigVersion;
use App\Models\Greenhouse;
use App\Models\GrowCycle;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Models\ChannelBinding;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigPresetService;
use App\Services\AutomationConfigRegistry;
use App\Services\SystemAutomationSettingsCatalog;
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
            $this->authorizeScopeAccess($request, $scopeType, $scopeId);
            $document = $this->documents->getDocument($namespace, $scopeType, $scopeId, true);

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
            $this->authorizeScopeAccess($request, $scopeType, $scopeId);
            $payload = $request->input('payload');
            if (! is_array($payload)) {
                throw new \InvalidArgumentException('payload must be an array/object.');
            }

            $previousDocument = $this->documents->getDocument($namespace, $scopeType, $scopeId, false);
            $previousPayload = is_array($previousDocument?->payload) ? $previousDocument->payload : [];
            $document = $this->documents->upsertDocument(
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
            $this->authorizeScopeAccess($request, $scopeType, $scopeId);

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

        if ($namespace === AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION) {
            $serialized = array_merge($serialized, $this->serializeZoneCorrectionDocument($scopeId, $payload));
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
            'resolved_config' => is_array($payload['resolved_config'] ?? null) ? $payload['resolved_config'] : [
                'base' => ZoneCorrectionConfigCatalog::defaults(),
                'phases' => [],
            ],
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

    private function authorizeScopeAccess(Request $request, string $scopeType, int $scopeId): void
    {
        $user = $request->user();
        if (! $user) {
            abort(401, 'Unauthorized');
        }

        if ($scopeType === AutomationConfigRegistry::SCOPE_SYSTEM) {
            if (! $user->isAdmin()) {
                abort(403, 'Forbidden: Access denied to system automation config');
            }

            return;
        }

        if ($scopeType === AutomationConfigRegistry::SCOPE_GREENHOUSE) {
            $greenhouse = Greenhouse::query()->findOrFail($scopeId);
            if (! ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse)) {
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
}
