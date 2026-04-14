<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Http\Requests\SetupWizardGreenhouseClimateDevicesRequest;
use App\Http\Requests\SetupWizardValidateDevicesRequest;
use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\InfrastructureInstance;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\ValidationException;

class SetupWizardController extends Controller
{
    /**
     * @var array<int, string>
     */
    private const REQUIRED_ASSIGNMENT_ROLES = ['irrigation', 'ph_correction', 'ec_correction'];

    /**
     * @var array<int, string>
     */
    private const ALL_ASSIGNMENT_ROLES = [
        'irrigation',
        'ph_correction',
        'ec_correction',
        'accumulation',
        'climate',
        'light',
        'soil_moisture_sensor',
        'co2_sensor',
        'co2_actuator',
        'root_vent_actuator',
    ];

    /**
     * Серверная валидация обязательного набора устройств для шага 4 мастера настройки.
     */
    public function validateDevices(SetupWizardValidateDevicesRequest $request): JsonResponse
    {
        $validated = $request->validated();
        $user = $request->user();

        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $zoneId = (int) $validated['zone_id'];
        if (! ZoneAccessHelper::canAccessZone($user, $zoneId)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to target zone',
            ], 403);
        }

        $resolved = $this->resolveAssignments($validated, $zoneId, $user);
        $assignments = $resolved['assignments'];

        return response()->json([
            'status' => 'ok',
            'data' => [
                'validated' => true,
                'zone_id' => $zoneId,
                'required_roles' => [
                    'irrigation' => (int) $assignments['irrigation'],
                    'ph_correction' => (int) $assignments['ph_correction'],
                    'ec_correction' => (int) $assignments['ec_correction'],
                    'accumulation' => (int) $assignments['accumulation'],
                ],
            ],
        ]);
    }

    /**
     * Сохранить channel bindings для выбранных ролей шага 4 мастера настройки.
     */
    public function applyDeviceBindings(SetupWizardValidateDevicesRequest $request): JsonResponse
    {
        $validated = $request->validated();
        $user = $request->user();

        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $zoneId = (int) $validated['zone_id'];
        if (! ZoneAccessHelper::canAccessZone($user, $zoneId)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to target zone',
            ], 403);
        }

        $resolved = $this->resolveAssignments($validated, $zoneId, $user);
        $assignments = $resolved['assignments'];
        $nodes = $resolved['nodes'];

        $appliedBindings = [];
        DB::transaction(function () use ($zoneId, $assignments, $nodes, &$appliedBindings) {
            foreach ($this->bindingSpecs() as $spec) {
                $assignmentRole = $spec['assignment_role'];
                $nodeId = $assignments[$assignmentRole] ?? null;

                if (! is_numeric($nodeId)) {
                    if (! $spec['required']) {
                        $this->deleteBindingsByRole($zoneId, $spec['binding_role']);
                    }
                    continue;
                }

                $node = $nodes->get((int) $nodeId);
                if (! $node) {
                    continue;
                }

                $channelId = $this->findFirstMatchingActuatorChannelId($node, $spec['channel_candidates']);
                if (($spec['direction'] ?? 'actuator') === 'sensor') {
                    $channelId = $this->findFirstMatchingChannelId($node, $spec['channel_candidates'], 'sensor');
                }
                if ($channelId === null) {
                    if ($spec['required']) {
                        throw ValidationException::withMessages([
                            "assignments.{$assignmentRole}" => [
                                "Для роли {$this->roleLabel($assignmentRole)} не найден подходящий канал на узле {$node->uid}.",
                            ],
                        ]);
                    }
                    $this->deleteBindingsByRole($zoneId, $spec['binding_role']);
                    continue;
                }

                $instance = InfrastructureInstance::query()->firstOrCreate(
                    [
                        'owner_type' => 'zone',
                        'owner_id' => $zoneId,
                        'label' => $spec['label'],
                    ],
                    [
                        'asset_type' => $spec['asset_type'],
                        'required' => $spec['required'],
                    ]
                );

                if (
                    $instance->asset_type !== $spec['asset_type']
                    || (bool) $instance->required !== (bool) $spec['required']
                ) {
                    $instance->asset_type = $spec['asset_type'];
                    $instance->required = $spec['required'];
                    $instance->save();
                }

                $this->deleteBindingsByRole($zoneId, $spec['binding_role']);

                ChannelBinding::query()->updateOrCreate(
                    ['node_channel_id' => $channelId],
                    [
                        'infrastructure_instance_id' => $instance->id,
                        'direction' => $spec['direction'] ?? 'actuator',
                        'role' => $spec['binding_role'],
                    ]
                );

                $appliedBindings[] = [
                    'assignment_role' => $assignmentRole,
                    'binding_role' => $spec['binding_role'],
                    'node_id' => (int) $node->id,
                    'node_uid' => (string) $node->uid,
                    'channel_id' => $channelId,
                ];
            }
        });

        return response()->json([
            'status' => 'ok',
            'data' => [
                'validated' => true,
                'zone_id' => $zoneId,
                'required_roles' => [
                    'irrigation' => (int) $assignments['irrigation'],
                    'ph_correction' => (int) $assignments['ph_correction'],
                    'ec_correction' => (int) $assignments['ec_correction'],
                    'accumulation' => (int) $assignments['accumulation'],
                ],
                'applied_bindings' => $appliedBindings,
            ],
        ]);
    }

    public function validateGreenhouseClimateDevices(SetupWizardGreenhouseClimateDevicesRequest $request): JsonResponse
    {
        [$greenhouse, $nodesByRole, $enabled] = $this->resolveGreenhouseClimateBindings($request);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'validated' => true,
                'enabled' => $enabled,
                'greenhouse_id' => $greenhouse->id,
                'roles' => [
                    'climate_sensors' => array_values($nodesByRole['climate_sensor']->keys()->all()),
                    'weather_station_sensors' => array_values($nodesByRole['weather_station_sensor']->keys()->all()),
                    'vent_actuators' => array_values($nodesByRole['vent_actuator']->keys()->all()),
                    'fan_actuators' => array_values($nodesByRole['fan_actuator']->keys()->all()),
                ],
            ],
        ]);
    }

    public function applyGreenhouseClimateBindings(SetupWizardGreenhouseClimateDevicesRequest $request): JsonResponse
    {
        [$greenhouse, $nodesByRole, $enabled] = $this->resolveGreenhouseClimateBindings($request);

        $appliedBindings = [];

        DB::transaction(function () use ($greenhouse, $nodesByRole, &$appliedBindings): void {
            foreach ($this->greenhouseClimateBindingSpecs() as $spec) {
                $role = $spec['binding_role'];
                $nodes = $nodesByRole[$role] ?? collect();

                $this->deleteBindingsByRoleForOwner('greenhouse', (int) $greenhouse->id, $role);

                foreach ($nodes as $node) {
                    if (! $node instanceof DeviceNode) {
                        continue;
                    }

                    $channelIds = $this->findMatchingChannelIds(
                        $node,
                        $spec['channel_candidates'],
                        $spec['direction']
                    );

                    if ($channelIds === []) {
                        throw ValidationException::withMessages([
                            $role => ["Для роли {$this->roleLabel($role)} не найден подходящий канал на узле {$node->uid}."],
                        ]);
                    }

                    $instance = InfrastructureInstance::query()->create([
                        'owner_type' => 'greenhouse',
                        'owner_id' => $greenhouse->id,
                        'label' => "{$spec['label']} · {$node->uid}",
                        'asset_type' => $spec['asset_type'],
                        'required' => (bool) $spec['required'],
                    ]);

                    foreach ($channelIds as $channelId) {
                        ChannelBinding::query()->updateOrCreate(
                            ['node_channel_id' => $channelId],
                            [
                                'infrastructure_instance_id' => $instance->id,
                                'direction' => $spec['direction'],
                                'role' => $role,
                            ]
                        );

                        $appliedBindings[] = [
                            'binding_role' => $role,
                            'node_id' => (int) $node->id,
                            'node_uid' => (string) $node->uid,
                            'channel_id' => (int) $channelId,
                        ];
                    }
                }
            }

            $this->cleanupEmptyInfrastructureInstances('greenhouse', (int) $greenhouse->id);
        });

        return response()->json([
            'status' => 'ok',
            'data' => [
                'validated' => true,
                'enabled' => $enabled,
                'greenhouse_id' => $greenhouse->id,
                'applied_bindings' => $appliedBindings,
            ],
        ]);
    }

    /**
     * @param  array<string, mixed>  $validated
     * @param  mixed  $user
     * @return array{assignments: array<string, mixed>, nodes: Collection<int, DeviceNode>}
     */
    private function resolveAssignments(array $validated, int $zoneId, mixed $user): array
    {
        $assignments = is_array($validated['assignments'] ?? null) ? $validated['assignments'] : [];

        if (! is_numeric($assignments['accumulation'] ?? null) && is_numeric($assignments['irrigation'] ?? null)) {
            $assignments['accumulation'] = (int) $assignments['irrigation'];
        }

        if (
            is_numeric($assignments['irrigation'] ?? null)
            && is_numeric($assignments['accumulation'] ?? null)
            && (int) $assignments['irrigation'] !== (int) $assignments['accumulation']
        ) {
            throw ValidationException::withMessages([
                'assignments.accumulation' => ['Накопительный узел должен совпадать с узлом полива.'],
            ]);
        }

        $requiredNodeIds = array_map(
            static fn (string $role): int => (int) ($assignments[$role] ?? 0),
            self::REQUIRED_ASSIGNMENT_ROLES
        );

        if (count(array_unique($requiredNodeIds)) !== count($requiredNodeIds)) {
            throw ValidationException::withMessages([
                'assignments' => ['Обязательные роли должны быть назначены на разные узлы.'],
            ]);
        }

        $allNodeIds = [];
        foreach (self::ALL_ASSIGNMENT_ROLES as $role) {
            $value = $assignments[$role] ?? null;
            if (is_int($value) || is_numeric($value)) {
                $allNodeIds[] = (int) $value;
            }
        }

        if (($validated['selected_node_ids'] ?? null) && is_array($validated['selected_node_ids'])) {
            foreach ($validated['selected_node_ids'] as $nodeId) {
                $allNodeIds[] = (int) $nodeId;
            }
        }

        $allNodeIds = array_values(array_unique($allNodeIds));

        /** @var Collection<int, DeviceNode> $nodes */
        $nodes = DeviceNode::query()
            ->with('channels')
            ->whereIn('id', $allNodeIds)
            ->get()
            ->keyBy('id');

        if ($nodes->count() !== count($allNodeIds)) {
            throw ValidationException::withMessages([
                'assignments' => ['Часть выбранных узлов не найдена. Обновите список устройств и повторите попытку.'],
            ]);
        }

        foreach ($allNodeIds as $nodeId) {
            $node = $nodes->get($nodeId);
            if (! $node) {
                continue;
            }

            if (! ZoneAccessHelper::canAccessNode($user, $node)) {
                throw ValidationException::withMessages([
                    'assignments' => ["Нет доступа к узлу #{$nodeId}."],
                ]);
            }

            if ($node->zone_id !== null && (int) $node->zone_id !== $zoneId) {
                throw ValidationException::withMessages([
                    'assignments' => ["Узел {$node->uid} уже привязан к другой зоне."],
                ]);
            }
        }

        foreach (self::ALL_ASSIGNMENT_ROLES as $role) {
            $nodeId = $assignments[$role] ?? null;
            if (! is_numeric($nodeId)) {
                continue;
            }

            $node = $nodes->get((int) $nodeId);
            if (! $node) {
                continue;
            }

            if (! $this->matchesRole($node, $role)) {
                throw ValidationException::withMessages([
                    "assignments.{$role}" => ["Узел {$node->uid} не подходит для роли {$this->roleLabel($role)}."],
                ]);
            }
        }

        return [
            'assignments' => $assignments,
            'nodes' => $nodes,
        ];
    }

    /**
     * @return array<int, array{
     *   assignment_role:string,
     *   binding_role:string,
     *   label:string,
     *   asset_type:string,
     *   required:bool,
     *   channel_candidates:array<int, string>,
     *   direction:string
     * }>
     */
    private function bindingSpecs(): array
    {
        return [
            [
                'assignment_role' => 'irrigation',
                'binding_role' => 'pump_main',
                'label' => 'Основная помпа',
                'asset_type' => 'PUMP',
                'required' => true,
                'channel_candidates' => ['pump_main'],
                'direction' => 'actuator',
            ],
            [
                'assignment_role' => 'irrigation',
                'binding_role' => 'drain',
                'label' => 'Дренаж',
                'asset_type' => 'DRAIN',
                'required' => true,
                'channel_candidates' => ['drain', 'drain_main', 'drain_valve', 'valve_solution_supply', 'valve_solution_fill', 'valve_irrigation'],
                'direction' => 'actuator',
            ],
            [
                'assignment_role' => 'ph_correction',
                'binding_role' => 'pump_acid',
                'label' => 'Насос pH кислоты',
                'asset_type' => 'PUMP',
                'required' => true,
                'channel_candidates' => ['pump_acid'],
                'direction' => 'actuator',
            ],
            [
                'assignment_role' => 'ph_correction',
                'binding_role' => 'pump_base',
                'label' => 'Насос pH щёлочи',
                'asset_type' => 'PUMP',
                'required' => true,
                'channel_candidates' => ['pump_base'],
                'direction' => 'actuator',
            ],
            [
                'assignment_role' => 'ec_correction',
                'binding_role' => 'pump_a',
                'label' => 'Насос EC NPK',
                'asset_type' => 'PUMP',
                'required' => true,
                'channel_candidates' => ['pump_a'],
                'direction' => 'actuator',
            ],
            [
                'assignment_role' => 'ec_correction',
                'binding_role' => 'pump_b',
                'label' => 'Насос EC Calcium',
                'asset_type' => 'PUMP',
                'required' => true,
                'channel_candidates' => ['pump_b'],
                'direction' => 'actuator',
            ],
            [
                'assignment_role' => 'ec_correction',
                'binding_role' => 'pump_c',
                'label' => 'Насос EC Magnesium',
                'asset_type' => 'PUMP',
                'required' => true,
                'channel_candidates' => ['pump_c'],
                'direction' => 'actuator',
            ],
            [
                'assignment_role' => 'ec_correction',
                'binding_role' => 'pump_d',
                'label' => 'Насос EC Micro',
                'asset_type' => 'PUMP',
                'required' => true,
                'channel_candidates' => ['pump_d'],
                'direction' => 'actuator',
            ],
            [
                'assignment_role' => 'climate',
                'binding_role' => 'vent',
                'label' => 'Вентиляция',
                'asset_type' => 'FAN',
                'required' => false,
                'channel_candidates' => ['vent', 'vent_drive', 'vent_window_pct', 'fan', 'fan_air'],
                'direction' => 'actuator',
            ],
            [
                'assignment_role' => 'climate',
                'binding_role' => 'heater',
                'label' => 'Обогрев',
                'asset_type' => 'HEATER',
                'required' => false,
                'channel_candidates' => ['heater', 'heater_air'],
                'direction' => 'actuator',
            ],
            [
                'assignment_role' => 'light',
                'binding_role' => 'light',
                'label' => 'Освещение',
                'asset_type' => 'LIGHT',
                'required' => false,
                'channel_candidates' => ['light', 'light_main', 'white_light', 'uv_light'],
                'direction' => 'actuator',
            ],
            [
                'assignment_role' => 'soil_moisture_sensor',
                'binding_role' => 'soil_moisture_sensor',
                'label' => 'Датчик влажности субстрата (soil moisture)',
                'asset_type' => 'OTHER',
                'required' => false,
                'channel_candidates' => ['soil_moisture', 'soil_moisture_pct', 'substrate_moisture'],
                'direction' => 'sensor',
            ],
            [
                'assignment_role' => 'co2_sensor',
                'binding_role' => 'co2_sensor',
                'label' => 'Датчик CO2 зоны',
                'asset_type' => 'OTHER',
                'required' => false,
                'channel_candidates' => ['co2_ppm'],
                'direction' => 'sensor',
            ],
            [
                'assignment_role' => 'co2_actuator',
                'binding_role' => 'co2_actuator',
                'label' => 'CO2 инжектор зоны',
                'asset_type' => 'CO2_INJECTOR',
                'required' => false,
                'channel_candidates' => ['co2_inject'],
                'direction' => 'actuator',
            ],
            [
                'assignment_role' => 'root_vent_actuator',
                'binding_role' => 'root_vent_actuator',
                'label' => 'Прикорневая вентиляция',
                'asset_type' => 'FAN',
                'required' => false,
                'channel_candidates' => ['root_vent', 'fan_root'],
                'direction' => 'actuator',
            ],
        ];
    }

    /**
     * @return array<int, array{
     *   request_key:string,
     *   binding_role:string,
     *   label:string,
     *   asset_type:string,
     *   required:bool,
     *   channel_candidates:array<int, string>,
     *   direction:string
     * }>
     */
    private function greenhouseClimateBindingSpecs(): array
    {
        return [
            [
                'request_key' => 'climate_sensors',
                'binding_role' => 'climate_sensor',
                'label' => 'Климат-сенсор',
                'asset_type' => 'OTHER',
                'required' => true,
                'channel_candidates' => ['temp_air', 'humidity_air', 'co2_ppm'],
                'direction' => 'sensor',
            ],
            [
                'request_key' => 'weather_station_sensors',
                'binding_role' => 'weather_station_sensor',
                'label' => 'Метеостанция',
                'asset_type' => 'OTHER',
                'required' => false,
                'channel_candidates' => ['outdoor_temp', 'outdoor_humidity', 'wind_speed', 'rain', 'pressure'],
                'direction' => 'sensor',
            ],
            [
                'request_key' => 'vent_actuators',
                'binding_role' => 'vent_actuator',
                'label' => 'Привод форточек',
                'asset_type' => 'VENT',
                'required' => false,
                'channel_candidates' => ['vent_drive', 'vent_window_pct'],
                'direction' => 'actuator',
            ],
            [
                'request_key' => 'fan_actuators',
                'binding_role' => 'fan_actuator',
                'label' => 'Вентилятор',
                'asset_type' => 'FAN',
                'required' => false,
                'channel_candidates' => ['fan_air'],
                'direction' => 'actuator',
            ],
        ];
    }

    /**
     * @param  array<int, string>  $candidates
     */
    private function findFirstMatchingActuatorChannelId(DeviceNode $node, array $candidates): ?int
    {
        return $this->findFirstMatchingChannelId($node, $candidates, 'actuator');
    }

    /**
     * @param  array<int, string>  $candidates
     */
    private function findFirstMatchingChannelId(DeviceNode $node, array $candidates, string $direction): ?int
    {
        $matches = $this->findMatchingChannelIds($node, $candidates, $direction);

        return $matches[0] ?? null;
    }

    /**
     * @param  array<int, string>  $candidates
     * @return array<int, int>
     */
    private function findMatchingChannelIds(DeviceNode $node, array $candidates, string $direction): array
    {
        $normalizedCandidates = array_map(static fn (string $channel): string => strtolower($channel), $candidates);
        $matches = [];

        foreach ($node->channels as $channel) {
            $name = strtolower((string) ($channel->channel ?? ''));
            if ($name === '' || ! in_array($name, $normalizedCandidates, true)) {
                continue;
            }

            $type = strtolower((string) ($channel->type ?? ''));
            if ($type !== '' && $type !== strtolower($direction)) {
                continue;
            }

            $matches[] = (int) $channel->id;
        }

        return array_values(array_unique($matches));
    }

    private function deleteBindingsByRole(int $zoneId, string $bindingRole): void
    {
        $this->deleteBindingsByRoleForOwner('zone', $zoneId, $bindingRole);
    }

    private function deleteBindingsByRoleForOwner(string $ownerType, int $ownerId, string $bindingRole): void
    {
        ChannelBinding::query()
            ->where('role', $bindingRole)
            ->whereHas('infrastructureInstance', function ($query) use ($ownerType, $ownerId) {
                $query->where('owner_type', $ownerType)
                    ->where('owner_id', $ownerId);
            })
            ->delete();
    }

    private function cleanupEmptyInfrastructureInstances(string $ownerType, int $ownerId): void
    {
        InfrastructureInstance::query()
            ->where('owner_type', $ownerType)
            ->where('owner_id', $ownerId)
            ->doesntHave('channelBindings')
            ->delete();
    }

    private function matchesRole(DeviceNode $node, string $role): bool
    {
        $type = strtolower((string) ($node->type ?? ''));
        $channels = $node->channels
            ->pluck('channel')
            ->map(static fn ($channel): string => strtolower((string) $channel))
            ->filter(static fn (string $channel): bool => $channel !== '')
            ->values()
            ->all();

        if ($role === 'irrigation') {
            return $type === 'irrig'
                || $this->hasAnyChannel($channels, [
                    'pump_main',
                    'valve_irrigation',
                    'valve_clean_fill',
                    'valve_clean_supply',
                    'valve_solution_fill',
                    'valve_solution_supply',
                    'level_clean_min',
                    'level_clean_max',
                    'level_solution_min',
                    'level_solution_max',
                    'water_level',
                    'pump_in',
                    'drain',
                    'drain_main',
                ]);
        }

        if ($role === 'ph_correction') {
            return $type === 'ph'
                || $this->hasAnyChannel($channels, ['ph_sensor', 'pump_acid', 'pump_base']);
        }

        if ($role === 'ec_correction') {
            return $type === 'ec'
                || $this->hasAnyChannel($channels, ['ec_sensor', 'pump_a', 'pump_b', 'pump_c', 'pump_d']);
        }

        if ($role === 'accumulation') {
            return $this->matchesRole($node, 'irrigation');
        }

        if ($role === 'climate') {
            return $type === 'climate'
                || $this->hasAnyChannel($channels, ['temp_air', 'air_temp_c', 'air_rh', 'humidity_air', 'co2_ppm', 'fan_air', 'heater_air', 'vent_drive']);
        }

        if ($role === 'light') {
            return $type === 'light'
                || $this->hasAnyChannel($channels, ['white_light', 'uv_light', 'light_main', 'light_level', 'lux_main']);
        }

        if ($role === 'soil_moisture_sensor') {
            return in_array($type, ['soil', 'substrate', 'climate'], true)
                || $this->hasAnyChannel($channels, ['soil_moisture', 'soil_moisture_pct', 'substrate_moisture']);
        }

        if ($role === 'co2_sensor') {
            return $type === 'climate'
                || $this->hasAnyChannel($channels, ['co2_ppm']);
        }

        if ($role === 'co2_actuator') {
            return $type === 'climate'
                || $this->hasAnyChannel($channels, ['co2_inject']);
        }

        if ($role === 'root_vent_actuator') {
            return $type === 'climate'
                || $this->hasAnyChannel($channels, ['root_vent', 'fan_root']);
        }

        if ($role === 'climate_sensor') {
            return $type === 'climate'
                || $this->hasAnyChannel($channels, ['temp_air', 'humidity_air', 'co2_ppm']);
        }

        if ($role === 'weather_station_sensor') {
            return $type === 'weather'
                || $this->hasAnyChannel($channels, ['outdoor_temp', 'outdoor_humidity', 'wind_speed', 'rain', 'pressure']);
        }

        if ($role === 'vent_actuator') {
            return $type === 'climate'
                || $this->hasAnyChannel($channels, ['vent_drive', 'vent_window_pct']);
        }

        if ($role === 'fan_actuator') {
            return $type === 'climate'
                || $this->hasAnyChannel($channels, ['fan_air']);
        }

        return false;
    }

    /**
     * @param array<int, string> $channels
     * @param array<int, string> $candidates
     */
    private function hasAnyChannel(array $channels, array $candidates): bool
    {
        $lookup = array_flip($channels);
        foreach ($candidates as $candidate) {
            if (array_key_exists(strtolower($candidate), $lookup)) {
                return true;
            }
        }

        return false;
    }

    private function roleLabel(string $role): string
    {
        return match ($role) {
            'irrigation' => 'полив + накопление',
            'ph_correction' => 'коррекция pH',
            'ec_correction' => 'коррекция EC',
            'accumulation' => 'накопительный узел (общий с поливом)',
            'climate' => 'климат',
            'light' => 'свет',
            'soil_moisture_sensor' => 'датчик влажности субстрата (soil moisture)',
            'co2_sensor' => 'датчик CO2 зоны',
            'co2_actuator' => 'CO2 инжектор зоны',
            'root_vent_actuator' => 'прикорневая вентиляция',
            'climate_sensor' => 'климат-сенсор теплицы',
            'weather_station_sensor' => 'метеостанция',
            'vent_actuator' => 'привод форточек',
            'fan_actuator' => 'вентилятор теплицы',
            default => $role,
        };
    }

    /**
     * @return array{0: Greenhouse, 1: array<string, Collection<int, DeviceNode>>, 2: bool}
     */
    private function resolveGreenhouseClimateBindings(SetupWizardGreenhouseClimateDevicesRequest $request): array
    {
        $validated = $request->validated();
        $user = $request->user();
        if (! $user) {
            abort(401, 'Unauthorized');
        }

        $greenhouse = Greenhouse::query()->findOrFail((int) $validated['greenhouse_id']);
        if (! ZoneAccessHelper::canAccessGreenhouseScope($user, $greenhouse)) {
            abort(403, 'Forbidden: Access denied to target greenhouse');
        }

        $enabled = (bool) ($validated['enabled'] ?? true);
        $roleToNodeIds = [
            'climate_sensor' => array_values(array_unique(array_map('intval', $validated['climate_sensors'] ?? []))),
            'weather_station_sensor' => array_values(array_unique(array_map('intval', $validated['weather_station_sensors'] ?? []))),
            'vent_actuator' => array_values(array_unique(array_map('intval', $validated['vent_actuators'] ?? []))),
            'fan_actuator' => array_values(array_unique(array_map('intval', $validated['fan_actuators'] ?? []))),
        ];

        if ($enabled && $roleToNodeIds['climate_sensor'] === []) {
            throw ValidationException::withMessages([
                'climate_sensors' => ['Нужен хотя бы один климатический сенсор теплицы.'],
            ]);
        }

        if ($enabled && $roleToNodeIds['vent_actuator'] === [] && $roleToNodeIds['fan_actuator'] === []) {
            throw ValidationException::withMessages([
                'vent_actuators' => ['Нужен хотя бы один actuator: форточки или вентилятор.'],
                'fan_actuators' => ['Нужен хотя бы один actuator: форточки или вентилятор.'],
            ]);
        }

        $allNodeIds = [];
        foreach ($roleToNodeIds as $nodeIds) {
            foreach ($nodeIds as $nodeId) {
                $allNodeIds[] = $nodeId;
            }
        }
        $allNodeIds = array_values(array_unique($allNodeIds));

        $nodes = DeviceNode::query()
            ->with(['channels', 'zone:id,greenhouse_id'])
            ->whereIn('id', $allNodeIds)
            ->get()
            ->keyBy('id');

        if ($nodes->count() !== count($allNodeIds)) {
            throw ValidationException::withMessages([
                'greenhouse_id' => ['Часть выбранных узлов не найдена. Обновите список устройств и повторите попытку.'],
            ]);
        }

        $nodesByRole = [];
        foreach ($roleToNodeIds as $role => $nodeIds) {
            $nodesByRole[$role] = collect();

            foreach ($nodeIds as $nodeId) {
                $node = $nodes->get($nodeId);
                if (! $node instanceof DeviceNode) {
                    continue;
                }

                if (! ZoneAccessHelper::canAccessNode($user, $node)) {
                    throw ValidationException::withMessages([
                        $role => ["Нет доступа к узлу #{$nodeId}."],
                    ]);
                }

                $nodeGreenhouseId = (int) ($node->zone?->greenhouse_id ?? 0);
                if ($node->zone_id !== null && $nodeGreenhouseId !== (int) $greenhouse->id) {
                    throw ValidationException::withMessages([
                        $role => ["Узел {$node->uid} уже относится к другой теплице."],
                    ]);
                }

                if (! $this->matchesRole($node, $role)) {
                    throw ValidationException::withMessages([
                        $role => ["Узел {$node->uid} не подходит для роли {$this->roleLabel($role)}."],
                    ]);
                }

                $nodesByRole[$role]->put((int) $node->id, $node);
            }
        }

        return [$greenhouse, $nodesByRole, $enabled];
    }
}
