<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\ChannelBinding;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Services\ZoneReadinessService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class ZoneInfrastructureController extends Controller
{
    /**
     * Получить инфраструктуру зоны
     * GET /zones/{zone}/infrastructure
     */
    public function show(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверяем доступ к зоне
        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $infrastructure = InfrastructureInstance::query()
            ->where(function ($query) use ($zone) {
                $query->where(function ($query) use ($zone) {
                    $query->where('owner_type', 'zone')
                        ->where('owner_id', $zone->id);
                })->orWhere(function ($query) use ($zone) {
                    $query->where('owner_type', 'greenhouse')
                        ->where('owner_id', $zone->greenhouse_id);
                });
            })
            ->with(['channelBindings.nodeChannel.node:id,uid,name', 'channelBindings.nodeChannel'])
            ->get();

        $isValid = $zone->isInfrastructureValid();
        $missingAssets = $isValid ? [] : $zone->getMissingRequiredAssets();

        // Получаем полную информацию о readiness
        $readinessService = app(ZoneReadinessService::class);
        $readiness = $readinessService->validate($zone->id);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'infrastructure' => $infrastructure,
                'is_valid' => $isValid,
                'missing_required_assets' => $missingAssets,
                'readiness' => $readiness,
            ],
        ]);
    }

    /**
     * Обновить инфраструктуру зоны
     * PUT /zones/{zone}/infrastructure
     */
    public function update(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверяем доступ к зоне
        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $data = $request->validate([
            'infrastructure' => ['required', 'array'],
            'infrastructure.*.asset_type' => ['required', 'string', 'in:PUMP,MISTER,TANK_CLEAN,TANK_WORKING,TANK_NUTRIENT,DRAIN,LIGHT,VENT,HEATER,FAN,CO2_INJECTOR,OTHER'],
            'infrastructure.*.label' => ['required', 'string', 'max:255'],
            'infrastructure.*.required' => ['sometimes', 'boolean'],
            'infrastructure.*.capacity_liters' => ['nullable', 'numeric', 'min:0'],
            'infrastructure.*.flow_rate' => ['nullable', 'numeric', 'min:0'],
            'infrastructure.*.specs' => ['nullable', 'array'],
        ]);

        try {
            DB::beginTransaction();

            // Удаляем старую инфраструктуру зоны (без greenhouse assets)
            InfrastructureInstance::query()
                ->where('owner_type', 'zone')
                ->where('owner_id', $zone->id)
                ->delete();

            // Создаем новую инфраструктуру
            foreach ($data['infrastructure'] as $item) {
                InfrastructureInstance::create([
                    'owner_type' => 'zone',
                    'owner_id' => $zone->id,
                    'asset_type' => $item['asset_type'],
                    'label' => $item['label'],
                    'required' => $item['required'] ?? false,
                    'capacity_liters' => $item['capacity_liters'] ?? null,
                    'flow_rate' => $item['flow_rate'] ?? null,
                    'specs' => $item['specs'] ?? null,
                ]);
            }

            DB::commit();

            // Загружаем обновленную инфраструктуру
            $infrastructure = InfrastructureInstance::query()
                ->where('owner_type', 'zone')
                ->where('owner_id', $zone->id)
                ->with(['channelBindings.nodeChannel.node:id,uid,name', 'channelBindings.nodeChannel'])
                ->get();

            $isValid = $zone->isInfrastructureValid();
            $missingAssets = $isValid ? [] : $zone->getMissingRequiredAssets();

            return response()->json([
                'status' => 'ok',
                'data' => [
                    'infrastructure' => $infrastructure,
                    'is_valid' => $isValid,
                    'missing_required_assets' => $missingAssets,
                ],
            ]);
        } catch (\Exception $e) {
            DB::rollBack();
            Log::error('ZoneInfrastructureController: Failed to update infrastructure', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Failed to update infrastructure: '.$e->getMessage(),
            ], 500);
        }
    }

    /**
     * Назначить канал к оборудованию
     * POST /zones/{zone}/infrastructure/bindings
     */
    public function storeBinding(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверяем доступ к зоне
        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $data = $request->validate([
            'infrastructure_instance_id' => ['required_without:asset_id', 'integer', 'exists:infrastructure_instances,id'],
            'asset_id' => ['required_without:infrastructure_instance_id', 'integer', 'exists:infrastructure_instances,id'],
            'node_channel_id' => ['required_without:node_id', 'integer', 'exists:node_channels,id'],
            'node_id' => ['required_without:node_channel_id', 'integer', 'exists:nodes,id'],
            'channel' => ['required_without:node_channel_id', 'string', 'max:255'],
            'direction' => ['required', 'string', 'in:actuator,sensor'],
            'role' => ['required', 'string', 'max:255'],
        ]);

        $instanceId = $data['infrastructure_instance_id'] ?? $data['asset_id'];
        // Проверяем, что инфраструктура принадлежит зоне или теплице зоны
        $asset = InfrastructureInstance::query()
            ->where('id', $instanceId)
            ->where(function ($query) use ($zone) {
                $query->where(function ($query) use ($zone) {
                    $query->where('owner_type', 'zone')
                        ->where('owner_id', $zone->id);
                })->orWhere(function ($query) use ($zone) {
                    $query->where('owner_type', 'greenhouse')
                        ->where('owner_id', $zone->greenhouse_id);
                });
            })
            ->first();

        if (! $asset) {
            return response()->json([
                'status' => 'error',
                'message' => 'Asset not found in this zone',
            ], 404);
        }

        if (! empty($data['node_channel_id'])) {
            $nodeChannel = NodeChannel::query()
                ->where('id', $data['node_channel_id'])
                ->whereHas('node', function ($query) use ($zone) {
                    $query->where('zone_id', $zone->id);
                })
                ->first();

            if (! $nodeChannel) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Node channel not found in this zone',
                ], 404);
            }
        } else {
            // Проверяем, что node принадлежит зоне
            $node = $zone->nodes()->where('id', $data['node_id'])->first();
            if (! $node) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Node not found in this zone',
                ], 404);
            }

            $nodeChannel = NodeChannel::query()
                ->where('node_id', $node->id)
                ->where('channel', $data['channel'])
                ->first();

            if (! $nodeChannel) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Channel not found in node',
                ], 404);
            }
        }

        try {
            // Удаляем существующую привязку для этого канала и роли, если есть
            ChannelBinding::query()
                ->where('infrastructure_instance_id', $asset->id)
                ->where('node_channel_id', $nodeChannel->id)
                ->where('role', $data['role'])
                ->delete();

            // Создаем новую привязку
            $binding = ChannelBinding::create([
                'infrastructure_instance_id' => $asset->id,
                'node_channel_id' => $nodeChannel->id,
                'direction' => $data['direction'],
                'role' => $data['role'],
            ]);

            $binding->load(['nodeChannel.node', 'infrastructureInstance']);

            return response()->json([
                'status' => 'ok',
                'data' => $binding,
            ], 201);
        } catch (\Exception $e) {
            Log::error('ZoneInfrastructureController: Failed to create binding', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Failed to create binding: '.$e->getMessage(),
            ], 500);
        }
    }

    /**
     * Удалить привязку канала
     * DELETE /zones/{zone}/infrastructure/bindings/{channelBinding}
     */
    public function destroyBinding(Request $request, Zone $zone, ChannelBinding $channelBinding): JsonResponse
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверяем доступ к зоне
        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $instance = $channelBinding->infrastructureInstance;
        if (! $instance) {
            return response()->json([
                'status' => 'error',
                'message' => 'Binding not linked to infrastructure instance',
            ], 404);
        }

        $allowed = ($instance->owner_type === 'zone' && $instance->owner_id === $zone->id)
            || ($instance->owner_type === 'greenhouse' && $instance->owner_id === $zone->greenhouse_id);

        if (! $allowed) {
            return response()->json([
                'status' => 'error',
                'message' => 'Binding not found in this zone',
            ], 404);
        }

        try {
            $channelBinding->delete();

            return response()->json([
                'status' => 'ok',
            ]);
        } catch (\Exception $e) {
            Log::error('ZoneInfrastructureController: Failed to delete binding', [
                'zone_id' => $zone->id,
                'binding_id' => $channelBinding->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Failed to delete binding: '.$e->getMessage(),
            ], 500);
        }
    }
}
