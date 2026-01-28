<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\ChannelBinding;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Services\ChannelBindingService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

class ChannelBindingController extends Controller
{
    public function __construct(
        private ChannelBindingService $bindingService
    ) {}

    /**
     * Создать привязку канала
     * POST /api/channel-bindings
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
            'infrastructure_instance_id' => ['required', 'integer', 'exists:infrastructure_instances,id'],
            'node_channel_id' => ['required', 'integer', 'exists:node_channels,id'],
            'direction' => ['required', 'string', 'in:actuator,sensor'],
            'role' => ['required', 'string', 'max:255'],
        ]);

        try {
            $instance = InfrastructureInstance::findOrFail($data['infrastructure_instance_id']);
            $nodeChannel = NodeChannel::query()
                ->with('node')
                ->where('id', $data['node_channel_id'])
                ->first();

            if (! $nodeChannel || ! $nodeChannel->node) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Node channel not found',
                ], 404);
            }

            // Проверяем доступ к владельцу
            if ($instance->owner_type === 'zone') {
                $zone = Zone::findOrFail($instance->owner_id);
                if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
                    return response()->json([
                        'status' => 'error',
                        'message' => 'Forbidden: Access denied to this zone',
                    ], 403);
                }
                if ($nodeChannel->node->zone_id !== $zone->id) {
                    return response()->json([
                        'status' => 'error',
                        'message' => 'Node channel not found in this zone',
                    ], 404);
                }
            } elseif ($instance->owner_type === 'greenhouse') {
                $zoneId = $nodeChannel->node->zone_id;
                $zone = $zoneId ? Zone::find($zoneId) : null;
                if (! $zone || $zone->greenhouse_id !== $instance->owner_id) {
                    return response()->json([
                        'status' => 'error',
                        'message' => 'Node channel not found in this greenhouse',
                    ], 404);
                }
            }

            $binding = $this->bindingService->create($data);

            return response()->json([
                'status' => 'ok',
                'data' => $binding,
            ], Response::HTTP_CREATED);
        } catch (\Exception $e) {
            Log::error('Failed to create channel binding', [
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
     * Обновить привязку канала
     * PATCH /api/channel-bindings/{channelBinding}
     */
    public function update(Request $request, ChannelBinding $channelBinding): JsonResponse
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $instance = $channelBinding->infrastructureInstance;

        // Проверяем доступ к владельцу
        if ($instance->owner_type === 'zone') {
            $zone = Zone::findOrFail($instance->owner_id);
            if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Forbidden: Access denied to this zone',
                ], 403);
            }
        }

        $data = $request->validate([
            'node_channel_id' => ['sometimes', 'required', 'integer', 'exists:node_channels,id'],
            'direction' => ['sometimes', 'required', 'string', 'in:actuator,sensor'],
            'role' => ['sometimes', 'required', 'string', 'max:255'],
        ]);

        try {
            if (! empty($data['node_channel_id'])) {
                $nodeChannel = NodeChannel::query()
                    ->with('node')
                    ->where('id', $data['node_channel_id'])
                    ->first();

                if (! $nodeChannel || ! $nodeChannel->node) {
                    return response()->json([
                        'status' => 'error',
                        'message' => 'Node channel not found',
                    ], 404);
                }

                if ($instance->owner_type === 'zone') {
                    $zone = Zone::findOrFail($instance->owner_id);
                    if ($nodeChannel->node->zone_id !== $zone->id) {
                        return response()->json([
                            'status' => 'error',
                            'message' => 'Node channel not found in this zone',
                        ], 404);
                    }
                } elseif ($instance->owner_type === 'greenhouse') {
                    $zoneId = $nodeChannel->node->zone_id;
                    $zone = $zoneId ? Zone::find($zoneId) : null;
                    if (! $zone || $zone->greenhouse_id !== $instance->owner_id) {
                        return response()->json([
                            'status' => 'error',
                            'message' => 'Node channel not found in this greenhouse',
                        ], 404);
                    }
                }
            }

            $binding = $this->bindingService->update($channelBinding, $data);

            return response()->json([
                'status' => 'ok',
                'data' => $binding,
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to update channel binding', [
                'binding_id' => $channelBinding->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Удалить привязку канала
     * DELETE /api/channel-bindings/{channelBinding}
     */
    public function destroy(ChannelBinding $channelBinding): JsonResponse
    {
        $user = request()->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $instance = $channelBinding->infrastructureInstance;

        // Проверяем доступ к владельцу
        if ($instance->owner_type === 'zone') {
            $zone = Zone::findOrFail($instance->owner_id);
            if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Forbidden: Access denied to this zone',
                ], 403);
            }
        }

        try {
            $this->bindingService->delete($channelBinding);

            return response()->json([
                'status' => 'ok',
                'message' => 'Channel binding deleted',
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to delete channel binding', [
                'binding_id' => $channelBinding->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }
}
