<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Services\AutomationScheduler\ScheduleWorkspaceService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ScheduleWorkspaceController extends Controller
{
    public function __construct(
        private readonly ScheduleWorkspaceService $scheduleWorkspaceService,
    ) {}

    public function show(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $horizon = (string) $request->query('horizon', '24h');
        $payload = $this->scheduleWorkspaceService->buildWorkspace($zone, $horizon);

        return response()->json([
            'status' => 'ok',
            'data' => $payload,
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
}
