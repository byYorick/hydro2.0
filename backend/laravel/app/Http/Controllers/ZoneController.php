<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Services\EffectiveTargetsService;
use App\Services\ZoneDataService;
use App\Services\ZoneLifecycleService;
use App\Services\ZoneOperationsService;
use App\Services\ZoneReadinessService;
use App\Services\ZoneService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\Log;

class ZoneController extends Controller
{
    public function __construct(
        private ZoneService $zoneService,
        private ZoneReadinessService $readinessService,
        private EffectiveTargetsService $effectiveTargetsService,
        private ZoneLifecycleService $lifecycleService,
        private ZoneOperationsService $operationsService,
        private ZoneDataService $dataService
    ) {}

    /**
     * Проверить авторизацию и доступ к зоне
     */
    private function authorizeZoneAccess($user, Zone $zone): void
    {
        if (! $user) {
            abort(401, 'Unauthorized');
        }

        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            abort(403, 'Forbidden: Access denied to this zone');
        }
    }

    public function index(Request $request): JsonResponse
    {
        $user = $request->user();
        if (! $user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Получаем доступные зоны для пользователя
        $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);

        // Валидация query параметров
        $validated = $request->validate([
            'greenhouse_id' => ['nullable', 'integer', 'exists:greenhouses,id'],
            'status' => ['nullable', 'string', 'in:online,offline,warning'],
            'search' => ['nullable', 'string', 'max:255'],
        ]);

        // Eager loading для предотвращения N+1 запросов
        $query = Zone::query()
            ->withCount('nodes') // Счетчик узлов
            ->with(['greenhouse:id,name', 'preset:id,name']); // Загружаем только нужные поля

        if (! $user?->isAdmin()) {
            $query->whereIn('id', $accessibleZoneIds ?: [0]);
        }

        // Фильтры
        if (isset($validated['greenhouse_id'])) {
            $query->where('greenhouse_id', $validated['greenhouse_id']);
        }

        if (isset($validated['status'])) {
            $query->where('status', $validated['status']);
        }

        if (isset($validated['search'])) {
            $query->where('name', 'ILIKE', '%'.$validated['search'].'%');
        }

        $zones = $query->orderBy('name')->get();

        return response()->json([
            'status' => 'ok',
            'data' => $zones,
        ]);
    }

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
            'name' => ['required', 'string', 'max:255'],
            'greenhouse_id' => ['required', 'integer', 'exists:greenhouses,id'],
            'preset_id' => ['nullable', 'integer', 'exists:presets,id'],
            'settings' => ['nullable', 'array'],
        ]);

        $zone = $this->zoneService->create($data);

        return response()->json([
            'status' => 'ok',
            'data' => $zone,
        ], Response::HTTP_CREATED);
    }

    public function show(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        // Eager loading
        $zone->load([
            'greenhouse:id,name',
            'preset:id,name',
            'activeGrowCycle.recipeRevision.recipe:id,name',
            'activeGrowCycle.currentPhase:id,name',
            'activeGrowCycle.plant:id,name',
        ]);

        return response()->json([
            'status' => 'ok',
            'data' => $zone,
        ]);
    }

    public function effectiveTargets(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        $cycle = $zone->activeGrowCycle;
        if (! $cycle) {
            return response()->json([
                'status' => 'ok',
                'data' => null,
            ]);
        }

        try {
            $effectiveTargets = $this->effectiveTargetsService->getEffectiveTargets($cycle->id);

            return response()->json([
                'status' => 'ok',
                'data' => $effectiveTargets,
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to get effective targets for zone', [
                'zone_id' => $zone->id,
                'cycle_id' => $cycle->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'ok',
                'data' => null,
                'warning' => 'Failed to load effective targets: '.$e->getMessage(),
            ]);
        }
    }

    public function update(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        $data = $request->validate([
            'name' => ['sometimes', 'string', 'max:255'],
            'greenhouse_id' => ['sometimes', 'integer', 'exists:greenhouses,id'],
            'preset_id' => ['nullable', 'integer', 'exists:presets,id'],
            'settings' => ['nullable', 'array'],
            'status' => ['sometimes', 'string', 'in:online,offline,warning'],
        ]);

        $zone = $this->zoneService->update($zone, $data);

        return response()->json([
            'status' => 'ok',
            'data' => $zone,
        ]);
    }

    public function destroy(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        try {
            $this->zoneService->delete($zone);

            return response()->json([
                'status' => 'ok',
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function pause(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        try {
            $this->lifecycleService->pause($zone);

            return response()->json(['status' => 'ok']);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function resume(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        try {
            $this->lifecycleService->resume($zone);

            return response()->json(['status' => 'ok']);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function harvest(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        try {
            $this->lifecycleService->harvest($zone);

            return response()->json(['status' => 'ok']);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function start(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        try {
            $this->lifecycleService->start($zone, []);

            return response()->json(['status' => 'ok']);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function health(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        $health = $this->operationsService->getHealth($zone);

        return response()->json([
            'status' => 'ok',
            'data' => $health,
        ]);
    }

    public function fill(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        $data = $request->validate([
            'target_level' => ['required', 'numeric', 'min:0.1', 'max:1.0'],
            'max_duration_sec' => ['nullable', 'integer', 'min:10', 'max:600'],
        ]);

        $jobId = $this->operationsService->fill($zone, $data);

        return response()->json([
            'status' => 'ok',
            'message' => 'Fill operation queued',
            'job_id' => $jobId,
        ], Response::HTTP_ACCEPTED);
    }

    public function drain(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        $data = $request->validate([
            'target_level' => ['required', 'numeric', 'min:0.0', 'max:0.9'],
            'max_duration_sec' => ['nullable', 'integer', 'min:10', 'max:600'],
        ]);

        $jobId = $this->operationsService->drain($zone, $data);

        return response()->json([
            'status' => 'ok',
            'message' => 'Drain operation queued',
            'job_id' => $jobId,
        ], Response::HTTP_ACCEPTED);
    }

    public function calibrateFlow(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        $data = $request->validate([
            'duration_sec' => ['required', 'integer', 'min:10', 'max:300'],
        ]);

        $jobId = $this->operationsService->calibrateFlow($zone, $data);

        return response()->json([
            'status' => 'ok',
            'message' => 'Calibrate flow operation queued',
            'job_id' => $jobId,
        ], Response::HTTP_ACCEPTED);
    }

    public function cycles(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        $result = $this->dataService->getCycles($zone, $request);

        return response()->json([
            'status' => 'ok',
            'data' => $result,
        ]);
    }

    public function unassignedErrors(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        $result = $this->dataService->getUnassignedErrors($zone, $request);

        return response()->json([
            'status' => 'ok',
            'data' => $result,
        ]);
    }

    public function snapshot(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        $snapshot = $this->dataService->getSnapshot($zone, $request);

        return response()->json([
            'status' => 'ok',
            'data' => $snapshot,
        ]);
    }

    public function events(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        $result = $this->dataService->getEvents($zone, $request);

        return response()->json([
            'status' => 'ok',
            'data' => $result,
        ]);
    }

    public function updateInfrastructure(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        $data = $request->validate([
            'infrastructure_id' => ['required', 'integer', 'exists:infrastructure_instances,id'],
        ]);

        $this->zoneService->updateInfrastructure($zone, $data['infrastructure_id']);

        return response()->json([
            'status' => 'ok',
        ]);
    }
}
