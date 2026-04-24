<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Services\AutomationScheduler\ExecutionRunReadModel;
use App\Services\Scheduler\ExecutionChainAssembler;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ScheduleExecutionController extends Controller
{
    public function __construct(
        private readonly ExecutionRunReadModel $executionRunReadModel,
        private readonly ExecutionChainAssembler $chainAssembler,
    ) {}

    public function show(Request $request, Zone $zone, string $executionId): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        if (preg_match('/^\d+$/', trim($executionId)) !== 1) {
            return response()->json([
                'status' => 'error',
                'code' => 'VALIDATION_ERROR',
                'message' => 'Некорректный execution_id',
            ], 422);
        }

        $payload = $this->executionRunReadModel->findForZone($zone->id, $executionId);
        if ($payload === null) {
            return response()->json([
                'status' => 'error',
                'code' => 'NOT_FOUND',
                'message' => 'Execution not found',
            ], 404);
        }

        $payload['chain'] = $this->chainAssembler->assemble($zone->id, $executionId);

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
