<?php

namespace App\Http\Controllers;

use App\Exceptions\ZoneRuntimeSwitchDeniedException;
use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use App\Services\EffectiveTargetsService;
use App\Services\ZoneDataService;
use App\Services\ZoneLifecycleService;
use App\Services\ZoneOperationsService;
use App\Services\ZoneReadinessService;
use App\Services\ZoneService;
use App\Support\ZoneNodeChannelScope;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\Log;

class ZoneController extends Controller
{
    public function __construct(
        private ZoneService $zoneService,
        private ZoneOperationsService $operationsService,
        private ZoneReadinessService $readinessService,
        private EffectiveTargetsService $effectiveTargetsService,
        private ZoneLifecycleService $lifecycleService,
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

        $zones = $query->orderBy('name')->paginate(25);

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
            'description' => ['nullable', 'string', 'max:1000'],
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
            'activeGrowCycle.recipeRevision.phases.stageTemplate:id,code,name',
            'activeGrowCycle.currentPhase',
            'activeGrowCycle.phases',
            'activeGrowCycle.plant:id,name',
            'channelBindings.nodeChannel:id,node_id,channel,type,metric',
            'channelBindings.nodeChannel.node:id,uid,name,type',
        ]);

        $bindings = $zone->channelBindings->map(function ($binding) {
            $channel = $binding->nodeChannel;
            $node = $channel?->node;

            return [
                'id' => (int) $binding->id,
                'role' => $binding->role,
                'direction' => $binding->direction,
                'node_channel_id' => $channel?->id !== null ? (int) $channel->id : null,
                'channel' => $channel?->channel,
                'channel_type' => $channel?->type,
                'metric' => $channel?->metric,
                'node_id' => $node?->id !== null ? (int) $node->id : null,
                'node_uid' => $node?->uid,
                'node_name' => $node?->name,
                'node_type' => $node?->type,
            ];
        })->values();

        $payload = $zone->toArray();
        $payload['channel_bindings'] = $bindings;

        return response()->json([
            'status' => 'ok',
            'data' => $payload,
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
            'automation_runtime' => ['sometimes', 'string', 'in:ae3'],
        ]);

        try {
            $zone = $this->zoneService->update($zone, $data);
        } catch (ZoneRuntimeSwitchDeniedException $e) {
            return response()->json([
                'status' => 'error',
                'code' => 'runtime_switch_denied_zone_busy',
                'message' => $e->getMessage(),
                'details' => $e->details(),
            ], Response::HTTP_CONFLICT);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

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

    public function calibratePump(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request->user(), $zone);

        $settings = app(AutomationConfigDocumentService::class)->getSystemPayloadByLegacyNamespace('pump_calibration', true);
        $durationMinSec = max(1, (int) ($settings['calibration_duration_min_sec'] ?? 1));
        $durationMaxSec = max($durationMinSec, (int) ($settings['calibration_duration_max_sec'] ?? 120));

        $data = $request->validate([
            'node_channel_id' => ['required', 'integer', 'exists:node_channels,id'],
            'duration_sec' => ['required', 'integer', 'min:1'],
            'actual_ml' => ['nullable', 'numeric', 'min:0.01', 'max:100000'],
            'skip_run' => ['nullable', 'boolean'],
            'component' => ['nullable', 'string', 'in:npk,calcium,magnesium,micro,ph_up,ph_down'],
            'test_volume_l' => ['nullable', 'numeric', 'min:0.1', 'max:100000'],
            'ec_before_ms' => ['nullable', 'numeric', 'min:0', 'max:20'],
            'ec_after_ms' => ['nullable', 'numeric', 'min:0', 'max:20'],
            'temperature_c' => ['nullable', 'numeric', 'min:0', 'max:50'],
            'run_token' => ['nullable', 'string', 'max:128'],
            'manual_override' => ['nullable', 'boolean'],
        ]);

        if ((int) $data['duration_sec'] < $durationMinSec || (int) $data['duration_sec'] > $durationMaxSec) {
            return response()->json([
                'status' => 'error',
                'message' => "duration_sec must be within [{$durationMinSec}, {$durationMaxSec}]",
                'errors' => [
                    'duration_sec' => ["duration_sec must be within [{$durationMinSec}, {$durationMaxSec}]"],
                ],
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        $channelBelongsToZone = ZoneNodeChannelScope::belongsToZone($zone->id, (int) $data['node_channel_id']);
        if (! $channelBelongsToZone) {
            return response()->json([
                'status' => 'error',
                'message' => 'node_channel_id must belong to the selected zone',
                'errors' => [
                    'node_channel_id' => ['node_channel_id must belong to the selected zone'],
                ],
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        if (
            isset($data['ec_before_ms'], $data['ec_after_ms'])
            && (float) $data['ec_after_ms'] <= (float) $data['ec_before_ms']
        ) {
            return response()->json([
                'status' => 'error',
                'message' => 'ec_after_ms must be greater than ec_before_ms',
                'errors' => [
                    'ec_after_ms' => ['ec_after_ms must be greater than ec_before_ms'],
                ],
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        $skipRun = (bool) ($data['skip_run'] ?? false);
        $manualOverride = (bool) ($data['manual_override'] ?? false);
        $hasActualMl = array_key_exists('actual_ml', $data) && $data['actual_ml'] !== null;
        if (! $skipRun && $hasActualMl) {
            return response()->json([
                'status' => 'error',
                'message' => 'actual_ml must be submitted in a separate save step after terminal DONE',
                'errors' => [
                    'actual_ml' => ['actual_ml must be submitted in a separate save step after terminal DONE'],
                ],
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
        if ($skipRun && $hasActualMl && ! $manualOverride && empty($data['run_token'])) {
            return response()->json([
                'status' => 'error',
                'message' => 'run_token is required when saving calibration after a physical run',
                'errors' => [
                    'run_token' => ['run_token is required when saving calibration after a physical run'],
                ],
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        try {
            $result = $this->operationsService->calibratePump($zone, $data);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        $resultStatus = (string) ($result['status'] ?? '');
        $httpStatus = $resultStatus === 'awaiting_actual_ml'
            ? Response::HTTP_ACCEPTED
            : Response::HTTP_OK;
        $message = $resultStatus === 'awaiting_actual_ml'
            ? 'Pump calibration run accepted'
            : 'Pump calibration saved';

        return response()->json([
            'status' => 'ok',
            'message' => $message,
            'data' => $result,
        ], $httpStatus);
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

        return response()->json(array_merge(['status' => 'ok'], $result));
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

        return response()->json(array_merge(['status' => 'ok'], $result));
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
