<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Http\Requests\SetupWizardValidateDevicesRequest;
use App\Models\DeviceNode;
use Illuminate\Http\JsonResponse;
use Illuminate\Validation\ValidationException;

class SetupWizardController extends Controller
{
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

        $assignments = $validated['assignments'];
        $requiredRoles = ['irrigation', 'correction', 'accumulation'];

        $requiredNodeIds = array_map(
            static fn (string $role): int => (int) $assignments[$role],
            $requiredRoles
        );

        if (count(array_unique($requiredNodeIds)) !== count($requiredNodeIds)) {
            throw ValidationException::withMessages([
                'assignments' => ['Обязательные роли должны быть назначены на разные узлы.'],
            ]);
        }

        $allNodeIds = [];
        foreach (['irrigation', 'correction', 'accumulation', 'climate', 'light'] as $role) {
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

        /** @var \Illuminate\Support\Collection<int, DeviceNode> $nodes */
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

        foreach ($requiredRoles as $role) {
            $nodeId = (int) $assignments[$role];
            $node = $nodes->get($nodeId);
            if (! $node) {
                continue;
            }

            if (! $this->matchesRole($node, $role)) {
                throw ValidationException::withMessages([
                    "assignments.{$role}" => ["Узел {$node->uid} не подходит для роли {$this->roleLabel($role)}."],
                ]);
            }
        }

        return response()->json([
            'status' => 'ok',
            'data' => [
                'validated' => true,
                'zone_id' => $zoneId,
                'required_roles' => [
                    'irrigation' => (int) $assignments['irrigation'],
                    'correction' => (int) $assignments['correction'],
                    'accumulation' => (int) $assignments['accumulation'],
                ],
            ],
        ]);
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
            return str_contains($type, 'irrig')
                || str_contains($type, 'pump')
                || $this->hasAnyChannel($channels, ['pump_irrigation', 'valve_irrigation', 'main_pump']);
        }

        if ($role === 'correction') {
            return str_contains($type, 'ph')
                || str_contains($type, 'ec')
                || $this->hasAnyChannel($channels, ['pump_acid', 'pump_base', 'pump_a', 'pump_b', 'pump_c', 'pump_d', 'ph_sensor', 'ec_sensor']);
        }

        if ($role === 'accumulation') {
            return str_contains($type, 'water')
                || str_contains($type, 'tank')
                || $this->hasAnyChannel($channels, ['water_level', 'pump_in', 'drain', 'drain_main']);
        }

        if ($role === 'climate') {
            return str_contains($type, 'climate')
                || $this->hasAnyChannel($channels, ['temp_air', 'air_temp_c', 'air_rh', 'humidity_air', 'co2_ppm', 'fan_air', 'heater_air', 'vent_drive']);
        }

        if ($role === 'light') {
            return str_contains($type, 'light')
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
            'correction' => 'коррекция',
            'accumulation' => 'накопительный узел',
            'climate' => 'климат',
            'light' => 'свет',
            default => $role,
        };
    }
}
