<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Greenhouse;
use App\Models\InfrastructureInstance;
use App\Models\Zone;
use App\Services\InfrastructureInstanceService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

class InfrastructureInstanceController extends Controller
{
    public function __construct(
        private InfrastructureInstanceService $infrastructureService
    ) {}

    /**
     * Получить все экземпляры инфраструктуры для зоны
     * GET /api/zones/{zone}/infrastructure-instances
     */
    public function indexForZone(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        try {
            $instances = $this->infrastructureService->getForZone($zone);

            return response()->json([
                'status' => 'ok',
                'data' => $instances,
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to get infrastructure instances for zone', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Получить все экземпляры инфраструктуры для теплицы
     * GET /api/greenhouses/{greenhouse}/infrastructure-instances
     */
    public function indexForGreenhouse(Request $request, Greenhouse $greenhouse): JsonResponse
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        if (! ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this greenhouse',
            ], 403);
        }

        try {
            $instances = $this->infrastructureService->getForGreenhouse($greenhouse);

            return response()->json([
                'status' => 'ok',
                'data' => $instances,
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to get infrastructure instances for greenhouse', [
                'greenhouse_id' => $greenhouse->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Создать экземпляр инфраструктуры
     * POST /api/infrastructure-instances
     */
    public function store(Request $request): JsonResponse
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $data = $request->validate([
            'owner_type' => ['required', 'string', 'in:zone,greenhouse'],
            'owner_id' => ['required', 'integer'],
            'asset_type' => ['required', 'string', 'in:PUMP,MISTER,TANK_CLEAN,TANK_WORKING,TANK_NUTRIENT,DRAIN,LIGHT,VENT,HEATER,FAN,CO2_INJECTOR,OTHER'],
            'label' => ['required', 'string', 'max:255'],
            'specs' => ['nullable', 'array'],
            'required' => ['nullable', 'boolean'],
        ]);

        try {
            // Проверяем доступ к владельцу
            if ($data['owner_type'] === 'zone') {
                $zone = Zone::findOrFail($data['owner_id']);
                if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
                    return response()->json([
                        'status' => 'error',
                        'message' => 'Forbidden: Access denied to this zone',
                    ], 403);
                }
            } elseif ($data['owner_type'] === 'greenhouse') {
                $greenhouse = Greenhouse::findOrFail($data['owner_id']);
                if (! ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse)) {
                    return response()->json([
                        'status' => 'error',
                        'message' => 'Forbidden: Access denied to this greenhouse',
                    ], 403);
                }
            }

            $instance = $this->infrastructureService->create($data);

            return response()->json([
                'status' => 'ok',
                'data' => $instance->load('channelBindings'),
            ], Response::HTTP_CREATED);
        } catch (\Exception $e) {
            Log::error('Failed to create infrastructure instance', [
                'data' => $data,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Обновить экземпляр инфраструктуры
     * PATCH /api/infrastructure-instances/{infrastructureInstance}
     */
    public function update(Request $request, InfrastructureInstance $infrastructureInstance): JsonResponse
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверяем доступ к владельцу
        if ($infrastructureInstance->owner_type === 'zone') {
            $zone = Zone::findOrFail($infrastructureInstance->owner_id);
            if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Forbidden: Access denied to this zone',
                ], 403);
            }
        } elseif ($infrastructureInstance->owner_type === 'greenhouse') {
            $greenhouse = Greenhouse::findOrFail($infrastructureInstance->owner_id);
            if (! ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse)) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Forbidden: Access denied to this greenhouse',
                ], 403);
            }
        }

        $data = $request->validate([
            'label' => ['sometimes', 'required', 'string', 'max:255'],
            'specs' => ['nullable', 'array'],
            'required' => ['nullable', 'boolean'],
        ]);

        try {
            $instance = $this->infrastructureService->update($infrastructureInstance, $data);

            return response()->json([
                'status' => 'ok',
                'data' => $instance,
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to update infrastructure instance', [
                'instance_id' => $infrastructureInstance->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Удалить экземпляр инфраструктуры
     * DELETE /api/infrastructure-instances/{infrastructureInstance}
     */
    public function destroy(InfrastructureInstance $infrastructureInstance): JsonResponse
    {
        $user = request()->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверяем доступ к владельцу
        if ($infrastructureInstance->owner_type === 'zone') {
            $zone = Zone::findOrFail($infrastructureInstance->owner_id);
            if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Forbidden: Access denied to this zone',
                ], 403);
            }
        } elseif ($infrastructureInstance->owner_type === 'greenhouse') {
            $greenhouse = Greenhouse::findOrFail($infrastructureInstance->owner_id);
            if (! ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse)) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Forbidden: Access denied to this greenhouse',
                ], 403);
            }
        }

        try {
            $this->infrastructureService->delete($infrastructureInstance);

            return response()->json([
                'status' => 'ok',
                'message' => 'Infrastructure instance deleted',
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to delete infrastructure instance', [
                'instance_id' => $infrastructureInstance->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }
}
