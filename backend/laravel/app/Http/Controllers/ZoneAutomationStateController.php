<?php

namespace App\Http\Controllers;

use App\Http\Controllers\Concerns\PresentsLocalizedApiErrors;
use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Services\ZoneAutomationStateService;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ZoneAutomationStateController extends Controller
{
    use PresentsLocalizedApiErrors;

    public function __construct(
        private readonly ZoneAutomationStateService $stateService,
    ) {}

    public function show(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        try {
            return response()->json($this->stateService->resolveForApi($zone));
        } catch (ConnectionException|RequestException) {
            return $this->localizedError('upstream_unavailable', null, 503);
        } catch (\Throwable) {
            return $this->localizedError('upstream_error', 'Ошибка при получении состояния автоматизации.', 503);
        }
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

    public static function invalidateZoneStateCache(int $zoneId): void
    {
        app(ZoneAutomationStateService::class)->invalidateZoneStateCache($zoneId);
    }
}
