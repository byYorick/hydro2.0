<?php

namespace App\Http\Controllers;

use App\Http\Requests\StoreZoneEstopRequest;
use App\Models\Zone;
use App\Services\ZoneEstopService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ZoneEstopController extends Controller
{
    public function __construct(
        private readonly ZoneEstopService $estop,
    ) {}

    public function show(Request $request, Zone $zone): JsonResponse
    {
        $this->authorize('view', $zone);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'zone_id' => $zone->id,
                'estop' => $this->estop->status($zone),
            ],
        ]);
    }

    public function store(StoreZoneEstopRequest $request, Zone $zone): JsonResponse
    {
        $action = (string) $request->validated('action');
        $this->authorize($action === 'release' ? 'releaseEstop' : 'engageEstop', $zone);

        $result = $this->estop->apply(
            $zone,
            $action,
            $request->user(),
            $request->validated('reason'),
        );

        return response()->json([
            'status' => 'ok',
            'data' => $result,
        ]);
    }
}
