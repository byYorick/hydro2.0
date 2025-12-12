<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Models\ZoneInfrastructure;
use App\Models\ZoneChannelBinding;
use App\Models\InfrastructureAsset;
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
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $infrastructure = $zone->infrastructure()
            ->with(['channelBindings.node:id,uid,name', 'channelBindings'])
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
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $data = $request->validate([
            'infrastructure' => ['required', 'array'],
            'infrastructure.*.asset_type' => ['required', 'string', 'in:PUMP,MISTER,TANK_NUTRIENT,TANK_CLEAN,DRAIN,LIGHT,VENT,HEATER'],
            'infrastructure.*.label' => ['required', 'string', 'max:255'],
            'infrastructure.*.required' => ['sometimes', 'boolean'],
            'infrastructure.*.capacity_liters' => ['nullable', 'numeric', 'min:0'],
            'infrastructure.*.flow_rate' => ['nullable', 'numeric', 'min:0'],
            'infrastructure.*.specs' => ['nullable', 'array'],
        ]);

        try {
            DB::beginTransaction();

            // Удаляем старую инфраструктуру
            $zone->infrastructure()->delete();

            // Создаем новую инфраструктуру
            foreach ($data['infrastructure'] as $item) {
                ZoneInfrastructure::create([
                    'zone_id' => $zone->id,
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
            $infrastructure = $zone->infrastructure()
                ->with(['channelBindings.node:id,uid,name', 'channelBindings'])
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
                'message' => 'Failed to update infrastructure: ' . $e->getMessage(),
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
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $data = $request->validate([
            'asset_id' => ['required', 'integer', 'exists:zone_infrastructure,id'],
            'node_id' => ['required', 'integer', 'exists:nodes,id'],
            'channel' => ['required', 'string', 'max:255'],
            'direction' => ['required', 'string', 'in:actuator,sensor'],
            'role' => ['required', 'string', 'max:255'],
        ]);

        // Проверяем, что asset принадлежит зоне
        $asset = ZoneInfrastructure::where('id', $data['asset_id'])
            ->where('zone_id', $zone->id)
            ->first();

        if (!$asset) {
            return response()->json([
                'status' => 'error',
                'message' => 'Asset not found in this zone',
            ], 404);
        }

        // Проверяем, что node принадлежит зоне
        $node = $zone->nodes()->where('id', $data['node_id'])->first();
        if (!$node) {
            return response()->json([
                'status' => 'error',
                'message' => 'Node not found in this zone',
            ], 404);
        }

        // Проверяем, что канал существует
        $channelExists = $node->channels()
            ->where('channel', $data['channel'])
            ->exists();

        if (!$channelExists) {
            return response()->json([
                'status' => 'error',
                'message' => 'Channel not found in node',
            ], 404);
        }

        try {
            // Удаляем существующую привязку для этого asset, если есть
            ZoneChannelBinding::where('asset_id', $data['asset_id'])
                ->where('node_id', $data['node_id'])
                ->where('channel', $data['channel'])
                ->delete();

            // Создаем новую привязку
            $binding = ZoneChannelBinding::create([
                'zone_id' => $zone->id,
                'asset_id' => $data['asset_id'],
                'node_id' => $data['node_id'],
                'channel' => $data['channel'],
                'direction' => $data['direction'],
                'role' => $data['role'],
            ]);

            $binding->load(['asset', 'node:id,uid,name']);

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
                'message' => 'Failed to create binding: ' . $e->getMessage(),
            ], 500);
        }
    }

    /**
     * Удалить привязку канала
     * DELETE /zones/{zone}/infrastructure/bindings/{zoneChannelBinding}
     */
    public function destroyBinding(Request $request, Zone $zone, ZoneChannelBinding $zoneChannelBinding): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        // Проверяем, что привязка принадлежит зоне
        if ($zoneChannelBinding->zone_id !== $zone->id) {
            return response()->json([
                'status' => 'error',
                'message' => 'Binding not found in this zone',
            ], 404);
        }

        try {
            $zoneChannelBinding->delete();

            return response()->json([
                'status' => 'ok',
            ]);
        } catch (\Exception $e) {
            Log::error('ZoneInfrastructureController: Failed to delete binding', [
                'zone_id' => $zone->id,
                'binding_id' => $zoneChannelBinding->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => 'Failed to delete binding: ' . $e->getMessage(),
            ], 500);
        }
    }
}

