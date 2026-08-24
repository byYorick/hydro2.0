<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Http\Controllers\Concerns\PresentsLocalizedApiErrors;
use App\Http\Requests\OperatorUnblockZoneRequest;
use App\Models\Zone;
use App\Services\ZoneOperatorUnblockService;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Log;

class ZoneAutomationOperatorUnblockController extends Controller
{
    use PresentsLocalizedApiErrors;

    public function __construct(
        private readonly ZoneOperatorUnblockService $unblock,
    ) {}

    public function store(OperatorUnblockZoneRequest $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $user = $request->user();
        if (! $user) {
            abort(401, 'Unauthorized');
        }

        $validated = $request->validated();

        try {
            $payload = $this->unblock->unblock(
                $zone,
                $user,
                (string) $validated['reason'],
                (string) ($validated['source'] ?? 'frontend_operator_unblock'),
            );
        } catch (RequestException $e) {
            $proxyResponse = $this->buildAutomationEngineErrorResponse(
                $e,
                'Automation-engine ещё не поддерживает operator-unblock API.',
            );
            if ($proxyResponse instanceof JsonResponse) {
                return $proxyResponse;
            }

            Log::warning('ZoneAutomationOperatorUnblockController: automation-engine request failed', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return $this->localizedError('upstream_error', 'Ошибка при разблокировке зоны.', 503);
        } catch (ConnectionException $e) {
            Log::warning('ZoneAutomationOperatorUnblockController: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return $this->localizedError('upstream_unavailable', null, 503);
        }

        ZoneAutomationStateController::invalidateZoneStateCache($zone->id);

        return response()->json($payload);
    }

    private function authorizeZoneAccess(OperatorUnblockZoneRequest $request, Zone $zone): void
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
