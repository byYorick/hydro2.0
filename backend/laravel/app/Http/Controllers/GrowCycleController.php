<?php

namespace App\Http\Controllers;

use App\Events\GrowCycleUpdated;
use App\Models\GrowCycle;
use App\Models\Zone;
use App\Enums\GrowCycleStatus;
use App\Helpers\ZoneAccessHelper;
use App\Models\ZoneEvent;
use App\Models\GrowCycleTransition;
use App\Services\GrowCycleService;
use App\Services\GrowCyclePresenter;
use App\Services\EffectiveTargetsService;
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
        private GrowCyclePresenter $growCyclePresenter,
        private EffectiveTargetsService $effectiveTargetsService
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
            'recipe_revision_id' => ['required', 'integer', 'exists:recipe_revisions,id'],
            'plant_id' => ['required', 'integer', 'exists:plants,id'],
            'planting_at' => ['nullable', 'date'],
            'batch_label' => ['nullable', 'string', 'max:255'],
            'notes' => ['nullable', 'string'],
            'start_immediately' => ['nullable', 'boolean'],
        ]);

        try {
            // Проверяем, что в зоне нет активного цикла
            $activeCycle = $zone->activeGrowCycle;
            if ($activeCycle) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Zone already has an active cycle. Please pause, harvest, or abort it first.',
                ], Response::HTTP_UNPROCESSABLE_ENTITY);
            }

            $revision = \App\Models\RecipeRevision::findOrFail($data['recipe_revision_id']);

            // Проверяем, что ревизия опубликована
            if ($revision->status !== 'PUBLISHED') {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Only PUBLISHED revisions can be used for new cycles',
                ], Response::HTTP_UNPROCESSABLE_ENTITY);
            }

            // Получаем первую фазу
            $firstPhase = $revision->phases()->orderBy('phase_index')->first();
            if (!$firstPhase) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Revision has no phases',
                ], Response::HTTP_UNPROCESSABLE_ENTITY);
            }

            return DB::transaction(function () use ($zone, $revision, $firstPhase, $data, $user) {
                // Создаем новый цикл
                $plantingAt = isset($data['planting_at']) && $data['planting_at'] 
                    ? Carbon::parse($data['planting_at']) 
                    : now();

                $cycle = GrowCycle::create([
                    'greenhouse_id' => $zone->greenhouse_id,
                    'zone_id' => $zone->id,
                    'plant_id' => $data['plant_id'],
                    'recipe_revision_id' => $revision->id,
                    'current_phase_id' => $firstPhase->id,
                    'current_step_id' => null,
                    'status' => ($data['start_immediately'] ?? false) ? GrowCycleStatus::RUNNING : GrowCycleStatus::PLANNED,
                    'planting_at' => $plantingAt,
                    'phase_started_at' => ($data['start_immediately'] ?? false) ? $plantingAt : null,
                    'batch_label' => $data['batch_label'] ?? null,
                    'notes' => $data['notes'] ?? null,
                    'started_at' => ($data['start_immediately'] ?? false) ? $plantingAt : null,
                ]);

                // Логируем создание
                GrowCycleTransition::create([
                    'grow_cycle_id' => $cycle->id,
                    'from_phase_id' => null,
                    'to_phase_id' => $firstPhase->id,
                    'trigger' => 'CYCLE_CREATED',
                    'triggered_by' => $user->id,
                    'comment' => 'Cycle created',
                ]);

                // Записываем событие
                DB::table('zone_events')->insert([
                    'zone_id' => $zone->id,
                    'type' => 'CYCLE_CREATED',
                    'entity_type' => 'grow_cycle',
                    'entity_id' => (string) $cycle->id,
                    'payload_json' => json_encode([
                        'cycle_id' => $cycle->id,
                        'recipe_revision_id' => $revision->id,
                        'plant_id' => $data['plant_id'],
                        'user_id' => $user->id,
                        'user_name' => $user->name ?? 'Unknown',
                        'source' => 'web',
                    ]),
                    'created_at' => now()->setTimezone('UTC'),
                ]);

                // Отправляем WebSocket broadcast
                broadcast(new GrowCycleUpdated($cycle, 'CREATED'));

                return response()->json([
                    'status' => 'ok',
                    'data' => $cycle->load('recipeRevision', 'currentPhase', 'plant'),
                ], Response::HTTP_CREATED);
            });
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
     * Получить активный цикл с effective targets и прогрессом
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

        $cycle = $zone->activeGrowCycle;
        
        if (!$cycle) {
            return response()->json([
                'status' => 'ok',
                'data' => null,
            ]);
        }

        try {
            // Получаем effective targets
            $effectiveTargets = $this->effectiveTargetsService->getEffectiveTargets($cycle->id);

            // Формируем DTO для UI
            $dto = $this->growCyclePresenter->buildCycleDto($cycle);
            $dto['effective_targets'] = $effectiveTargets;

            return response()->json([
                'status' => 'ok',
                'data' => $dto,
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to get active cycle with targets', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            // Возвращаем цикл без targets в случае ошибки
            $dto = $this->growCyclePresenter->buildCycleDto($cycle);
            return response()->json([
                'status' => 'ok',
                'data' => $dto,
                'warning' => 'Failed to load effective targets: ' . $e->getMessage(),
            ]);
        }
    }

    /**
     * Получить активный цикл (legacy метод для совместимости)
     * GET /api/zones/{zone}/grow-cycle (alias)
     */
    public function getActive(Request $request, Zone $zone): JsonResponse
    {
        return $this->show($request, $zone);
    }

    /**
     * Переход на следующую фазу
     * POST /api/grow-cycles/{id}/advance-phase
     */
    public function advancePhase(Request $request, GrowCycle $growCycle): JsonResponse
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
            $revision = $growCycle->recipeRevision;
            if (!$revision) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Cycle has no recipe revision',
                ], Response::HTTP_UNPROCESSABLE_ENTITY);
            }

            $currentPhase = $growCycle->currentPhase;
            if (!$currentPhase) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Cycle has no current phase',
                ], Response::HTTP_UNPROCESSABLE_ENTITY);
            }

            // Находим следующую фазу
            $nextPhase = $revision->phases()
                ->where('phase_index', '>', $currentPhase->phase_index)
                ->orderBy('phase_index')
                ->first();

            if (!$nextPhase) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'No next phase available',
                ], Response::HTTP_UNPROCESSABLE_ENTITY);
            }

            return DB::transaction(function () use ($growCycle, $currentPhase, $nextPhase, $zone, $user) {
                // Обновляем цикл
                $growCycle->update([
                    'current_phase_id' => $nextPhase->id,
                    'current_step_id' => null, // Сбрасываем шаг
                    'phase_started_at' => now(),
                    'step_started_at' => null,
                ]);

                // Логируем переход
                GrowCycleTransition::create([
                    'grow_cycle_id' => $growCycle->id,
                    'from_phase_id' => $currentPhase->id,
                    'to_phase_id' => $nextPhase->id,
                    'from_step_id' => $growCycle->current_step_id,
                    'to_step_id' => null,
                    'trigger' => 'MANUAL',
                    'triggered_by' => $user->id,
                    'comment' => 'Advanced to next phase',
                ]);

                // Записываем событие в zone_events
                DB::table('zone_events')->insert([
                    'zone_id' => $zone->id,
                    'type' => 'CYCLE_PHASE_ADVANCED',
                    'entity_type' => 'grow_cycle',
                    'entity_id' => (string) $growCycle->id,
                    'payload_json' => json_encode([
                        'cycle_id' => $growCycle->id,
                        'from_phase_id' => $currentPhase->id,
                        'to_phase_id' => $nextPhase->id,
                        'user_id' => $user->id,
                        'user_name' => $user->name ?? 'Unknown',
                        'source' => 'web',
                    ]),
                    'created_at' => now()->setTimezone('UTC'),
                ]);

                // Отправляем WebSocket broadcast
                broadcast(new GrowCycleUpdated($growCycle->fresh(), 'PHASE_ADVANCED'));

                return response()->json([
                    'status' => 'ok',
                    'data' => $growCycle->fresh()->load('currentPhase', 'currentStep'),
                ]);
            });
        } catch (\Exception $e) {
            Log::error('Failed to advance phase', [
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
     * Установить конкретную фазу (manual switch с комментарием)
     * POST /api/grow-cycles/{id}/set-phase
     */
    public function setPhase(Request $request, GrowCycle $growCycle): JsonResponse
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
            'phase_id' => ['required', 'integer', 'exists:recipe_revision_phases,id'],
            'comment' => ['required', 'string', 'max:1000'],
        ]);

        try {
            $revision = $growCycle->recipeRevision;
            if (!$revision) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Cycle has no recipe revision',
                ], Response::HTTP_UNPROCESSABLE_ENTITY);
            }

            $newPhase = $revision->phases()->findOrFail($data['phase_id']);
            $currentPhase = $growCycle->currentPhase;

            return DB::transaction(function () use ($growCycle, $currentPhase, $newPhase, $data, $zone, $user) {
                // Обновляем цикл
                $growCycle->update([
                    'current_phase_id' => $newPhase->id,
                    'current_step_id' => null,
                    'phase_started_at' => now(),
                    'step_started_at' => null,
                ]);

                // Логируем переход
                GrowCycleTransition::create([
                    'grow_cycle_id' => $growCycle->id,
                    'from_phase_id' => $currentPhase?->id,
                    'to_phase_id' => $newPhase->id,
                    'from_step_id' => $growCycle->current_step_id,
                    'to_step_id' => null,
                    'trigger' => 'MANUAL',
                    'triggered_by' => $user->id,
                    'comment' => $data['comment'],
                ]);

                // Записываем событие в zone_events
                DB::table('zone_events')->insert([
                    'zone_id' => $zone->id,
                    'type' => 'CYCLE_PHASE_SET',
                    'entity_type' => 'grow_cycle',
                    'entity_id' => (string) $growCycle->id,
                    'payload_json' => json_encode([
                        'cycle_id' => $growCycle->id,
                        'from_phase_id' => $currentPhase?->id,
                        'to_phase_id' => $newPhase->id,
                        'user_id' => $user->id,
                        'user_name' => $user->name ?? 'Unknown',
                        'source' => 'web',
                        'comment' => $data['comment'],
                    ]),
                    'created_at' => now()->setTimezone('UTC'),
                ]);

                // Отправляем WebSocket broadcast
                broadcast(new GrowCycleUpdated($growCycle->fresh(), 'PHASE_SET'));

                return response()->json([
                    'status' => 'ok',
                    'data' => $growCycle->fresh()->load('currentPhase', 'currentStep'),
                ]);
            });
        } catch (\Exception $e) {
            Log::error('Failed to set phase', [
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
     * Сменить ревизию рецепта
     * POST /api/grow-cycles/{id}/change-recipe-revision
     */
    public function changeRecipeRevision(Request $request, GrowCycle $growCycle): JsonResponse
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
            'recipe_revision_id' => ['required', 'integer', 'exists:recipe_revisions,id'],
            'apply_mode' => ['required', 'string', 'in:now,next_phase'],
        ]);

        try {
            $newRevision = \App\Models\RecipeRevision::findOrFail($data['recipe_revision_id']);

            // Проверяем, что ревизия опубликована
            if ($newRevision->status !== 'PUBLISHED') {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Only PUBLISHED revisions can be applied to cycles',
                ], Response::HTTP_UNPROCESSABLE_ENTITY);
            }

            return DB::transaction(function () use ($growCycle, $newRevision, $data, $zone, $user) {
                if ($data['apply_mode'] === 'now') {
                    // Применяем сейчас: меняем ревизию и сбрасываем фазу на первую
                    $firstPhase = $newRevision->phases()->orderBy('phase_index')->first();
                    
                    if (!$firstPhase) {
                        return response()->json([
                            'status' => 'error',
                            'message' => 'Revision has no phases',
                        ], Response::HTTP_UNPROCESSABLE_ENTITY);
                    }

                    $oldRevisionId = $growCycle->recipe_revision_id;
                    $oldPhaseId = $growCycle->current_phase_id;

                    $growCycle->update([
                        'recipe_revision_id' => $newRevision->id,
                        'current_phase_id' => $firstPhase->id,
                        'current_step_id' => null,
                        'phase_started_at' => now(),
                        'step_started_at' => null,
                    ]);

                    // Логируем переход
                    GrowCycleTransition::create([
                        'grow_cycle_id' => $growCycle->id,
                        'from_phase_id' => $oldPhaseId,
                        'to_phase_id' => $firstPhase->id,
                        'trigger' => 'RECIPE_REVISION_CHANGED',
                        'triggered_by' => $user->id,
                        'comment' => "Changed recipe revision from {$oldRevisionId} to {$newRevision->id}",
                    ]);

                    // Записываем событие
                    DB::table('zone_events')->insert([
                        'zone_id' => $zone->id,
                        'type' => 'CYCLE_RECIPE_REVISION_CHANGED',
                        'entity_type' => 'grow_cycle',
                        'entity_id' => (string) $growCycle->id,
                        'payload_json' => json_encode([
                            'cycle_id' => $growCycle->id,
                            'from_revision_id' => $oldRevisionId,
                            'to_revision_id' => $newRevision->id,
                            'apply_mode' => 'now',
                            'user_id' => $user->id,
                            'user_name' => $user->name ?? 'Unknown',
                            'source' => 'web',
                        ]),
                        'created_at' => now()->setTimezone('UTC'),
                    ]);
                } else {
                    // Применяем с следующей фазы: только меняем ревизию, фазу не трогаем
                    $oldRevisionId = $growCycle->recipe_revision_id;
                    
                    $growCycle->update([
                        'recipe_revision_id' => $newRevision->id,
                    ]);

                    // Записываем событие
                    DB::table('zone_events')->insert([
                        'zone_id' => $zone->id,
                        'type' => 'CYCLE_RECIPE_REVISION_CHANGED',
                        'entity_type' => 'grow_cycle',
                        'entity_id' => (string) $growCycle->id,
                        'payload_json' => json_encode([
                            'cycle_id' => $growCycle->id,
                            'from_revision_id' => $oldRevisionId,
                            'to_revision_id' => $newRevision->id,
                            'apply_mode' => 'next_phase',
                            'user_id' => $user->id,
                            'user_name' => $user->name ?? 'Unknown',
                            'source' => 'web',
                        ]),
                        'created_at' => now()->setTimezone('UTC'),
                    ]);
                }

                // Отправляем WebSocket broadcast
                broadcast(new GrowCycleUpdated($growCycle->fresh(), 'RECIPE_REVISION_CHANGED'));

                return response()->json([
                    'status' => 'ok',
                    'data' => $growCycle->fresh()->load('recipeRevision', 'currentPhase'),
                ]);
            });
        } catch (\Exception $e) {
            Log::error('Failed to change recipe revision', [
                'cycle_id' => $growCycle->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

}
