<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Http\Requests\SetupWizardValidateDevicesRequest;
use App\Models\ChannelBinding;
use App\Models\DeviceNode;
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
    private const REQUIRED_ASSIGNMENT_ROLES = ['irrigation', 'ph_correction', 'ec_correction', 'accumulation'];

    /**
     * @var array<int, string>
     */
    private const ALL_ASSIGNMENT_ROLES = ['irrigation', 'ph_correction', 'ec_correction', 'accumulation', 'climate', 'light'];

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
                        'direction' => 'actuator',
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

    /**
     * @param  array<string, mixed>  $validated
     * @param  mixed  $user
     * @return array{assignments: array<string, mixed>, nodes: Collection<int, DeviceNode>}
     */
    private function resolveAssignments(array $validated, int $zoneId, mixed $user): array
    {
        $assignments = is_array($validated['assignments'] ?? null) ? $validated['assignments'] : [];

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
     *   channel_candidates:array<int, string>
     * }>
     */
    private function bindingSpecs(): array
    {
        return [
            [
                'assignment_role' => 'irrigation',
                'binding_role' => 'main_pump',
                'label' => 'Основная помпа',
                'asset_type' => 'PUMP',
                'required' => true,
                'channel_candidates' => ['main_pump', 'pump_main', 'pump_irrigation', 'valve_irrigation', 'pump_in'],
            ],
            [
                'assignment_role' => 'accumulation',
                'binding_role' => 'drain',
                'label' => 'Дренаж',
                'asset_type' => 'DRAIN',
                'required' => true,
                'channel_candidates' => ['drain', 'drain_main', 'drain_valve'],
            ],
            [
                'assignment_role' => 'ph_correction',
                'binding_role' => 'ph_acid_pump',
                'label' => 'Насос pH кислоты',
                'asset_type' => 'PUMP',
                'required' => true,
                'channel_candidates' => ['pump_acid', 'ph_acid_pump'],
            ],
            [
                'assignment_role' => 'ph_correction',
                'binding_role' => 'ph_base_pump',
                'label' => 'Насос pH щёлочи',
                'asset_type' => 'PUMP',
                'required' => true,
                'channel_candidates' => ['pump_base', 'ph_base_pump'],
            ],
            [
                'assignment_role' => 'ec_correction',
                'binding_role' => 'ec_npk_pump',
                'label' => 'Насос EC NPK',
                'asset_type' => 'PUMP',
                'required' => true,
                'channel_candidates' => ['pump_a', 'ec_npk_pump'],
            ],
            [
                'assignment_role' => 'ec_correction',
                'binding_role' => 'ec_calcium_pump',
                'label' => 'Насос EC Calcium',
                'asset_type' => 'PUMP',
                'required' => true,
                'channel_candidates' => ['pump_b', 'ec_calcium_pump'],
            ],
            [
                'assignment_role' => 'ec_correction',
                'binding_role' => 'ec_magnesium_pump',
                'label' => 'Насос EC Magnesium',
                'asset_type' => 'PUMP',
                'required' => true,
                'channel_candidates' => ['pump_c', 'ec_magnesium_pump'],
            ],
            [
                'assignment_role' => 'ec_correction',
                'binding_role' => 'ec_micro_pump',
                'label' => 'Насос EC Micro',
                'asset_type' => 'PUMP',
                'required' => true,
                'channel_candidates' => ['pump_d', 'ec_micro_pump'],
            ],
            [
                'assignment_role' => 'climate',
                'binding_role' => 'vent',
                'label' => 'Вентиляция',
                'asset_type' => 'FAN',
                'required' => false,
                'channel_candidates' => ['vent', 'vent_drive', 'vent_window_pct', 'fan', 'fan_air'],
            ],
            [
                'assignment_role' => 'climate',
                'binding_role' => 'heater',
                'label' => 'Обогрев',
                'asset_type' => 'HEATER',
                'required' => false,
                'channel_candidates' => ['heater', 'heater_air'],
            ],
            [
                'assignment_role' => 'light',
                'binding_role' => 'light',
                'label' => 'Освещение',
                'asset_type' => 'LIGHT',
                'required' => false,
                'channel_candidates' => ['light', 'light_main', 'white_light', 'uv_light'],
            ],
        ];
    }

    /**
     * @param  array<int, string>  $candidates
     */
    private function findFirstMatchingActuatorChannelId(DeviceNode $node, array $candidates): ?int
    {
        $normalizedCandidates = array_map(static fn (string $channel): string => strtolower($channel), $candidates);

        foreach ($node->channels as $channel) {
            $name = strtolower((string) ($channel->channel ?? ''));
            if ($name === '' || ! in_array($name, $normalizedCandidates, true)) {
                continue;
            }

            $type = strtolower((string) ($channel->type ?? ''));
            if ($type !== '' && $type !== 'actuator') {
                continue;
            }

            return (int) $channel->id;
        }

        return null;
    }

    private function deleteBindingsByRole(int $zoneId, string $bindingRole): void
    {
        ChannelBinding::query()
            ->where('role', $bindingRole)
            ->whereHas('infrastructureInstance', function ($query) use ($zoneId) {
                $query->where('owner_type', 'zone')
                    ->where('owner_id', $zoneId);
            })
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
                || $this->hasAnyChannel($channels, ['pump_irrigation', 'valve_irrigation', 'main_pump']);
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
            return in_array($type, ['water_sensor', 'recirculation'], true)
                || $this->hasAnyChannel($channels, ['water_level', 'pump_in', 'drain', 'drain_main']);
        }

        if ($role === 'climate') {
            return $type === 'climate'
                || $this->hasAnyChannel($channels, ['temp_air', 'air_temp_c', 'air_rh', 'humidity_air', 'co2_ppm', 'fan_air', 'heater_air', 'vent_drive']);
        }

        if ($role === 'light') {
            return $type === 'light'
                || $this->hasAnyChannel($channels, ['white_light', 'uv_light', 'light_main', 'light_level', 'lux_main']);
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
            'irrigation' => 'полив',
            'ph_correction' => 'коррекция pH',
            'ec_correction' => 'коррекция EC',
            'accumulation' => 'накопительный узел',
            'climate' => 'климат',
            'light' => 'свет',
            default => $role,
        };
    }
}
