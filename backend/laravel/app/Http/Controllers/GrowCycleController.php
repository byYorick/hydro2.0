<?php

namespace App\Http\Controllers;

use App\Events\GrowCycleUpdated;
use App\Models\GrowCycle;
use App\Models\Zone;
use App\Enums\GrowCycleStatus;
use App\Helpers\ZoneAccessHelper;
use App\Models\ZoneEvent;
use App\Services\GrowCycleService;
use App\Services\GrowCyclePresenter;
use Carbon\Carbon;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

class GrowCycleController extends Controller
{
    public function __construct(
        private GrowCycleService $growCycleService,
        private GrowCyclePresenter $growCyclePresenter
    ) {
    }
    /**
     * Приостановить цикл
     */
    public function pause(Request $request, GrowCycle $growCycle): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $zone = $growCycle->zone;
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        try {
            if ($growCycle->status !== GrowCycleStatus::RUNNING) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Cycle is not running',
                ], Response::HTTP_UNPROCESSABLE_ENTITY);
            }

            $growCycle->update(['status' => GrowCycleStatus::PAUSED]);
            $growCycle->refresh();

            // Записываем событие в zone_events
            DB::table('zone_events')->insert([
                'zone_id' => $zone->id,
                'type' => 'CYCLE_PAUSED',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $growCycle->id,
                'payload_json' => json_encode([
                    'cycle_id' => $growCycle->id,
                    'user_id' => $user->id,
                    'user_name' => $user->name ?? 'Unknown',
                    'source' => 'web',
                ]),
                'created_at' => now()->setTimezone('UTC'),
            ]);

            // Отправляем WebSocket broadcast
            broadcast(new GrowCycleUpdated($growCycle, 'PAUSED'));

            Log::info('Grow cycle paused', [
                'zone_id' => $zone->id,
                'cycle_id' => $growCycle->id,
                'user_id' => $user->id,
            ]);

            return response()->json([
                'status' => 'ok',
                'data' => $growCycle->fresh(),
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to pause grow cycle', [
                'zone_id' => $zone->id,
                'cycle_id' => $growCycle->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Возобновить цикл
     */
    public function resume(Request $request, GrowCycle $growCycle): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $zone = $growCycle->zone;
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        try {
            if ($growCycle->status !== GrowCycleStatus::PAUSED) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Cycle is not paused',
                ], Response::HTTP_UNPROCESSABLE_ENTITY);
            }

            $growCycle->update(['status' => GrowCycleStatus::RUNNING]);
            $growCycle->refresh();

            // Записываем событие в zone_events
            DB::table('zone_events')->insert([
                'zone_id' => $zone->id,
                'type' => 'CYCLE_RESUMED',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $growCycle->id,
                'payload_json' => json_encode([
                    'cycle_id' => $growCycle->id,
                    'user_id' => $user->id,
                    'user_name' => $user->name ?? 'Unknown',
                    'source' => 'web',
                ]),
                'created_at' => now()->setTimezone('UTC'),
            ]);

            // Отправляем WebSocket broadcast
            broadcast(new GrowCycleUpdated($growCycle, 'RESUMED'));

            Log::info('Grow cycle resumed', [
                'zone_id' => $zone->id,
                'cycle_id' => $growCycle->id,
                'user_id' => $user->id,
            ]);

            return response()->json([
                'status' => 'ok',
                'data' => $growCycle->fresh(),
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to resume grow cycle', [
                'zone_id' => $zone->id,
                'cycle_id' => $growCycle->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Зафиксировать сбор (harvest) - закрывает цикл
     */
    public function harvest(Request $request, GrowCycle $growCycle): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $zone = $growCycle->zone;
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $data = $request->validate([
            'batch_label' => ['nullable', 'string', 'max:255'],
            'notes' => ['nullable', 'string'],
        ]);

        try {
            if ($growCycle->status === GrowCycleStatus::HARVESTED || $growCycle->status === GrowCycleStatus::ABORTED) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Cycle is already completed',
                ], Response::HTTP_UNPROCESSABLE_ENTITY);
            }

            DB::transaction(function () use ($growCycle, $data, $zone, $user) {
                $growCycle->update([
                    'status' => GrowCycleStatus::HARVESTED,
                    'actual_harvest_at' => now(),
                    'batch_label' => $data['batch_label'] ?? $growCycle->batch_label,
                    'notes' => $data['notes'] ?? $growCycle->notes,
                ]);
                $growCycle->refresh();

                // Записываем событие в zone_events
                DB::table('zone_events')->insert([
                    'zone_id' => $zone->id,
                    'type' => 'CYCLE_HARVESTED',
                    'entity_type' => 'grow_cycle',
                    'entity_id' => (string) $growCycle->id,
                    'payload_json' => json_encode([
                        'cycle_id' => $growCycle->id,
                        'user_id' => $user->id,
                        'user_name' => $user->name ?? 'Unknown',
                        'source' => 'web',
                        'batch_label' => $growCycle->batch_label,
                    ]),
                    'created_at' => now()->setTimezone('UTC'),
                ]);

                // Отправляем WebSocket broadcast
                broadcast(new GrowCycleUpdated($growCycle, 'HARVESTED'));
            });

            Log::info('Grow cycle harvested', [
                'zone_id' => $zone->id,
                'cycle_id' => $growCycle->id,
                'user_id' => $user->id,
            ]);

            return response()->json([
                'status' => 'ok',
                'data' => $growCycle->fresh(),
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to harvest grow cycle', [
                'zone_id' => $zone->id,
                'cycle_id' => $growCycle->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Аварийная остановка цикла
     */
    public function abort(Request $request, GrowCycle $growCycle): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $zone = $growCycle->zone;
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $data = $request->validate([
            'notes' => ['nullable', 'string'],
        ]);

        try {
            if ($growCycle->status === GrowCycleStatus::HARVESTED || $growCycle->status === GrowCycleStatus::ABORTED) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Cycle is already completed',
                ], Response::HTTP_UNPROCESSABLE_ENTITY);
            }

            DB::transaction(function () use ($growCycle, $data, $zone, $user) {
                $growCycle->update([
                    'status' => GrowCycleStatus::ABORTED,
                    'notes' => $data['notes'] ?? $growCycle->notes,
                ]);
                $growCycle->refresh();

                // Записываем событие в zone_events
                DB::table('zone_events')->insert([
                    'zone_id' => $zone->id,
                    'type' => 'CYCLE_ABORTED',
                    'entity_type' => 'grow_cycle',
                    'entity_id' => (string) $growCycle->id,
                    'payload_json' => json_encode([
                        'cycle_id' => $growCycle->id,
                        'user_id' => $user->id,
                        'user_name' => $user->name ?? 'Unknown',
                        'source' => 'web',
                        'reason' => $data['notes'] ?? 'Emergency abort',
                    ]),
                    'created_at' => now()->setTimezone('UTC'),
                ]);

                // Отправляем WebSocket broadcast
                broadcast(new GrowCycleUpdated($growCycle, 'ABORTED'));
            });

            Log::info('Grow cycle aborted', [
                'zone_id' => $zone->id,
                'cycle_id' => $growCycle->id,
                'user_id' => $user->id,
            ]);

            return response()->json([
                'status' => 'ok',
                'data' => $growCycle->fresh(),
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to abort grow cycle', [
                'zone_id' => $zone->id,
                'cycle_id' => $growCycle->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Сменить рецепт (создать новый цикл или rebase)
     */
    public function changeRecipe(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $data = $request->validate([
            'recipe_id' => ['required', 'integer', 'exists:recipes,id'],
            'action' => ['nullable', 'string', 'in:new_cycle,rebase'],
        ]);

        $action = $data['action'] ?? 'new_cycle';

        try {
            $activeCycle = $this->getActiveCycle($zone);

            if ($action === 'rebase' && $activeCycle) {
                // Rebase: обновляем рецепт текущего цикла
                $activeCycle->update([
                    'recipe_id' => $data['recipe_id'],
                    'zone_recipe_instance_id' => $zone->recipeInstance?->id,
                ]);

                ZoneEvent::create([
                    'zone_id' => $zone->id,
                    'type' => 'CYCLE_RECIPE_REBASED',
                    'details' => [
                        'cycle_id' => $activeCycle->id,
                        'recipe_id' => $data['recipe_id'],
                        'user_id' => $user->id,
                        'user_name' => $user->name ?? 'Unknown',
                        'source' => 'web',
                    ],
                    'created_at' => now()->setTimezone('UTC'),
                ]);

                return response()->json([
                    'status' => 'ok',
                    'data' => $activeCycle->fresh(),
                    'action' => 'rebase',
                ]);
            } else {
                // New cycle: создаем новый цикл
                // Если есть активный цикл, сначала завершаем его
                if ($activeCycle && $activeCycle->status === GrowCycleStatus::RUNNING) {
                    $activeCycle->update(['status' => GrowCycleStatus::ABORTED]);
                }

                $newCycle = GrowCycle::create([
                    'greenhouse_id' => $zone->greenhouse_id,
                    'zone_id' => $zone->id,
                    'recipe_id' => $data['recipe_id'],
                    'zone_recipe_instance_id' => $zone->recipeInstance?->id,
                    'status' => GrowCycleStatus::PLANNED,
                    'started_at' => now(),
                ]);

                ZoneEvent::create([
                    'zone_id' => $zone->id,
                    'type' => 'CYCLE_CREATED',
                    'details' => [
                        'cycle_id' => $newCycle->id,
                        'recipe_id' => $data['recipe_id'],
                        'user_id' => $user->id,
                        'user_name' => $user->name ?? 'Unknown',
                        'source' => 'web',
                    ],
                    'created_at' => now()->setTimezone('UTC'),
                ]);

                return response()->json([
                    'status' => 'ok',
                    'data' => $newCycle,
                    'action' => 'new_cycle',
                ]);
            }
        } catch (\Exception $e) {
            Log::error('Failed to change recipe for grow cycle', [
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
     * Создать и запустить цикл выращивания
     * POST /api/zones/{zone}/grow-cycles
     */
    public function store(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $data = $request->validate([
            'recipe_id' => ['nullable', 'integer', 'exists:recipes,id'],
            'plant_id' => ['nullable', 'integer', 'exists:plants,id'],
            'planting_at' => ['nullable', 'date'],
            'settings' => ['nullable', 'array'],
            'start_immediately' => ['nullable', 'boolean'],
        ]);

        try {
            $recipe = $data['recipe_id'] 
                ? \App\Models\Recipe::find($data['recipe_id'])
                : $zone->recipeInstance?->recipe;

            if (!$recipe) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Recipe is required',
                ], Response::HTTP_UNPROCESSABLE_ENTITY);
            }

            $cycle = $this->growCycleService->createCycle(
                $zone,
                $recipe,
                $data['plant_id'] ?? null,
                $data['settings'] ?? []
            );

            // Если start_immediately, запускаем цикл
            if ($data['start_immediately'] ?? false) {
                $plantingAt = isset($data['planting_at']) && $data['planting_at'] ? Carbon::parse($data['planting_at']) : null;
                $cycle = $this->growCycleService->startCycle($cycle, $plantingAt);
            }

            return response()->json([
                'status' => 'ok',
                'data' => $cycle,
            ], Response::HTTP_CREATED);
        } catch (\Exception $e) {
            Log::error('Failed to create grow cycle', [
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
     * Получить активный цикл с UI DTO
     * GET /api/zones/{zone}/grow-cycle
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

        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $cycle = $this->getActiveCycle($zone);
        
        if (!$cycle) {
            return response()->json([
                'status' => 'ok',
                'data' => null,
            ]);
        }

        // Формируем DTO для UI
        $dto = $this->growCyclePresenter->buildCycleDto($cycle);

        return response()->json([
            'status' => 'ok',
            'data' => $dto,
        ]);
    }

    /**
     * Переход на следующую стадию
     * POST /api/grow-cycles/{id}/advance-stage
     */
    public function advanceStage(Request $request, GrowCycle $growCycle): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $zone = $growCycle->zone;
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        $data = $request->validate([
            'target_stage_code' => ['nullable', 'string'],
        ]);

        try {
            $cycle = $this->growCycleService->advanceStage(
                $growCycle,
                $data['target_stage_code'] ?? null
            );

            // Логируем событие
            ZoneEvent::create([
                'zone_id' => $cycle->zone_id,
                'type' => 'STAGE_ADVANCED',
                'details' => [
                    'cycle_id' => $cycle->id,
                    'stage_code' => $cycle->current_stage_code,
                    'user_id' => $user->id,
                    'user_name' => $user->name ?? 'Unknown',
                    'source' => 'web',
                ],
                'created_at' => now()->setTimezone('UTC'),
            ]);

            return response()->json([
                'status' => 'ok',
                'data' => $cycle,
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to advance stage', [
                'cycle_id' => $growCycle->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Получить активный цикл для зоны
     */
    private function getActiveCycle(Zone $zone): ?GrowCycle
    {
        return GrowCycle::where('zone_id', $zone->id)
            ->whereIn('status', [GrowCycleStatus::PLANNED, GrowCycleStatus::RUNNING, GrowCycleStatus::PAUSED])
            ->latest('started_at')
            ->first();
    }
}
