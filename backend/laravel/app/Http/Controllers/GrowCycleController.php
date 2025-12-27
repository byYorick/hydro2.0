<?php

namespace App\Http\Controllers;

use App\Models\GrowCycle;
use App\Models\Zone;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Enums\GrowCycleStatus;
use App\Helpers\ZoneAccessHelper;
use App\Services\GrowCycleService;
use App\Services\GrowCyclePresenter;
use App\Services\EffectiveTargetsService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Gate;
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
     * Получить список всех grow cycles
     * GET /api/grow-cycles
     */
    public function index(Request $request): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Получить зоны, к которым пользователь имеет доступ
        $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);

        if (empty($accessibleZoneIds)) {
            return response()->json([
                'status' => 'ok',
                'data' => [],
            ]);
        }

        $cycles = GrowCycle::whereIn('zone_id', $accessibleZoneIds)
            ->with([
                'zone',
                'plant',
                'recipeRevision',
                'currentPhase',
            ])
            ->orderBy('created_at', 'desc')
            ->paginate($request->get('per_page', 50));

        return response()->json([
            'status' => 'ok',
            'data' => $cycles,
        ]);
    }
    /**
     * Запустить цикл (из PLANNED в RUNNING)
     * POST /api/grow-cycles/{id}/start
     */
    public function start(Request $request, GrowCycle $growCycle): JsonResponse
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

        // Проверка прав: только агроном может управлять циклами
        if (!Gate::allows('update', $growCycle)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Only agronomists can manage grow cycles',
            ], 403);
        }

        try {
            $cycle = $this->growCycleService->startCycle($growCycle);

            return response()->json([
                'status' => 'ok',
                'data' => $cycle,
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        } catch (\Exception $e) {
            Log::error('Failed to start grow cycle', [
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

        // Проверка прав: только агроном может управлять циклами
        if (!Gate::allows('update', $growCycle)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Only agronomists can manage grow cycles',
            ], 403);
        }

        try {
            $cycle = $this->growCycleService->pause($growCycle, $user->id);

            return response()->json([
                'status' => 'ok',
                'data' => $cycle,
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
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

        // Проверка прав: только агроном может управлять циклами
        if (!Gate::allows('update', $growCycle)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Only agronomists can manage grow cycles',
            ], 403);
        }

        try {
            $cycle = $this->growCycleService->resume($growCycle, $user->id);

            return response()->json([
                'status' => 'ok',
                'data' => $cycle,
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
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

        // Проверка прав: только агроном может управлять циклами
        if (!Gate::allows('update', $growCycle)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Only agronomists can manage grow cycles',
            ], 403);
        }

        $data = $request->validate([
            'batch_label' => ['nullable', 'string', 'max:255'],
            'notes' => ['nullable', 'string'],
        ]);

        try {
            $cycle = $this->growCycleService->harvest($growCycle, $data, $user->id);

            return response()->json([
                'status' => 'ok',
                'data' => $cycle,
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
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

        // Проверка прав: только агроном может управлять циклами
        if (!Gate::allows('update', $growCycle)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Only agronomists can manage grow cycles',
            ], 403);
        }

        $data = $request->validate([
            'notes' => ['nullable', 'string'],
        ]);

        try {
            $cycle = $this->growCycleService->abort($growCycle, $data, $user->id);

            return response()->json([
                'status' => 'ok',
                'data' => $cycle,
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
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

        // Проверка прав: только агроном может создавать циклы
        if (!Gate::allows('create', [GrowCycle::class, $zone])) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Only agronomists can create grow cycles',
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
            $revision = RecipeRevision::findOrFail($data['recipe_revision_id']);
            $cycle = $this->growCycleService->createCycle(
                $zone,
                $revision,
                $data['plant_id'],
                $data,
                $user->id
            );

            return response()->json([
                'status' => 'ok',
                'data' => $cycle,
            ], Response::HTTP_CREATED);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
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
     * Получить активный цикл
     * GET /api/zones/{zone}/grow-cycle
     */
    public function getActive(Request $request, Zone $zone): JsonResponse
    {
        return $this->show($request, $zone);
    }

    /**
     * Получить все циклы для теплицы
     * GET /api/greenhouses/{greenhouse}/grow-cycles
     */
    public function indexByGreenhouse(Request $request, \App\Models\Greenhouse $greenhouse): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        try {
            $cycles = $this->growCycleService->getByGreenhouse($greenhouse->id);

            return response()->json([
                'status' => 'ok',
                'data' => $cycles,
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to get grow cycles for greenhouse', [
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

        // Проверка прав: только агроном может переключать фазы
        if (!Gate::allows('switchPhase', $growCycle)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Only agronomists can switch phases',
            ], 403);
        }

        try {
            $cycle = $this->growCycleService->advancePhase($growCycle, $user->id);

            return response()->json([
                'status' => 'ok',
                'data' => $cycle,
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
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

        // Проверка прав: только агроном может переключать фазы
        if (!Gate::allows('switchPhase', $growCycle)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Only agronomists can switch phases',
            ], 403);
        }

        $data = $request->validate([
            'phase_id' => ['required', 'integer', 'exists:recipe_revision_phases,id'],
            'comment' => ['required', 'string', 'max:1000'],
        ]);

        try {
            $newPhase = RecipeRevisionPhase::findOrFail($data['phase_id']);
            $cycle = $this->growCycleService->setPhase($growCycle, $newPhase, $data['comment'], $user->id);

            return response()->json([
                'status' => 'ok',
                'data' => $cycle,
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
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

        // Проверка прав: только агроном может менять ревизию рецепта
        if (!Gate::allows('changeRecipeRevision', $growCycle)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Only agronomists can change recipe revisions',
            ], 403);
        }

        $data = $request->validate([
            'recipe_revision_id' => ['required', 'integer', 'exists:recipe_revisions,id'],
            'apply_mode' => ['required', 'string', 'in:now,next_phase'],
        ]);

        try {
            $newRevision = RecipeRevision::findOrFail($data['recipe_revision_id']);
            $cycle = $this->growCycleService->changeRecipeRevision(
                $growCycle,
                $newRevision,
                $data['apply_mode'],
                $user->id
            );

            return response()->json([
                'status' => 'ok',
                'data' => $cycle,
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
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
