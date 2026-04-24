<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Services\AutomationScheduler\ScheduleWorkspaceService;
use App\Services\Scheduler\ExecutionChainAssembler;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ScheduleWorkspaceController extends Controller
{
    public function __construct(
        private readonly ScheduleWorkspaceService $scheduleWorkspaceService,
        private readonly ExecutionChainAssembler $chainAssembler,
    ) {}

    public function show(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $horizon = (string) $request->query('horizon', '24h');
        $payload = $this->scheduleWorkspaceService->buildWorkspace($zone, $horizon);

        $activeRun = $payload['execution']['active_run'] ?? null;
        if (is_array($activeRun) && isset($activeRun['execution_id']) && is_string($activeRun['execution_id'])) {
            $activeRun['chain'] = $this->chainAssembler->assemble($zone->id, $activeRun['execution_id']);
            $payload['execution']['active_run'] = $activeRun;
        }

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
