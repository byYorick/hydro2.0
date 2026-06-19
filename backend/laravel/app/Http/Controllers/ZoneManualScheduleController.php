<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Http\Requests\StoreZoneManualScheduleRequest;
use App\Http\Requests\UpdateZoneManualScheduleRequest;
use App\Models\Zone;
use App\Models\ZoneManualSchedule;
use App\Services\AutomationScheduler\ManualScheduleService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ZoneManualScheduleController extends Controller
{
    public function __construct(
        private readonly ManualScheduleService $manualScheduleService,
    ) {}

    public function index(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        return response()->json([
            'status' => 'ok',
            'data' => $this->manualScheduleService->listForZone($zone->id),
        ]);
    }

    public function store(StoreZoneManualScheduleRequest $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneManage($request, $zone);

        $schedule = $this->manualScheduleService->create(
            zone: $zone,
            data: $request->validated(),
            actor: $request->user(),
        );

        return response()->json([
            'status' => 'ok',
            'data' => $this->manualScheduleService->serialize($schedule),
        ], 201);
    }

    public function update(
        UpdateZoneManualScheduleRequest $request,
        Zone $zone,
        ZoneManualSchedule $manualSchedule,
    ): JsonResponse {
        $this->authorizeZoneManage($request, $zone);
        $this->assertScheduleBelongsToZone($zone, $manualSchedule);

        $schedule = $this->manualScheduleService->update(
            schedule: $manualSchedule,
            data: $request->validated(),
        );

        return response()->json([
            'status' => 'ok',
            'data' => $this->manualScheduleService->serialize($schedule),
        ]);
    }

    public function destroy(Request $request, Zone $zone, ZoneManualSchedule $manualSchedule): JsonResponse
    {
        $this->authorizeZoneManage($request, $zone);
        $this->assertScheduleBelongsToZone($zone, $manualSchedule);

        $this->manualScheduleService->delete($manualSchedule);

        return response()->json([
            'status' => 'ok',
            'data' => ['deleted' => true],
        ]);
    }

    private function authorizeZoneAccess(Request $request, Zone $zone): void
    {
        $user = $request->user();
        if (! $user) {
            abort(401, 'Unauthorized');
        }

        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            abort(403, 'Forbidden: Access denied to this zone');
        }
    }

    private function authorizeZoneManage(Request $request, Zone $zone): void
    {
        $this->authorizeZoneAccess($request, $zone);

        $role = strtolower(trim((string) ($request->user()?->role ?? '')));
        if (! in_array($role, ['agronomist', 'admin'], true)) {
            abort(403, 'Forbidden: manual schedules require agronomist or admin role');
        }
    }

    private function assertScheduleBelongsToZone(Zone $zone, ZoneManualSchedule $manualSchedule): void
    {
        if ((int) $manualSchedule->zone_id !== (int) $zone->id) {
            abort(404, 'Manual schedule not found for this zone');
        }
    }
}
