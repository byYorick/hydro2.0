<?php

namespace App\Http\Controllers;

use App\Http\Controllers\Concerns\PresentsLocalizedApiErrors;
use App\Http\Requests\StoreZoneEstopRequest;
use App\Models\Zone;
use App\Services\ZoneEstopService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ZoneEstopController extends Controller
{
    use PresentsLocalizedApiErrors;

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

        if ($action === 'release' && ! $this->estop->canRelease($zone)) {
            return $this->localizedError('ae3_zone_lease_held',
                'Снятие E-STOP разрешено после завершения/разблокировки задачи AE3 и освобождения lease.', 409);
        }

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
