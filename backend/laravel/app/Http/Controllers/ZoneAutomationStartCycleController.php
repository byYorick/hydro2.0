<?php

namespace App\Http\Controllers;

use App\Http\Controllers\Concerns\PresentsLocalizedApiErrors;
use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Services\Ae3IrrigationBridgeService;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class ZoneAutomationStartCycleController extends Controller
{
    use PresentsLocalizedApiErrors;

    public function __construct(
        private readonly Ae3IrrigationBridgeService $bridge,
    ) {}

    public function store(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $validated = $request->validate([
            'source' => ['nullable', 'string', 'max:64'],
            'idempotency_key' => ['nullable', 'string', 'min:8', 'max:160'],
        ]);

        $payload = [
            'source' => $validated['source'] ?? 'laravel_api',
            'idempotency_key' => $validated['idempotency_key'] ?? $this->buildIdempotencyKey($zone->id),
        ];

        try {
            return response()->json($this->bridge->dispatchStartCycle($zone->id, $payload));
        } catch (RequestException $e) {
            $proxyResponse = $this->buildAutomationEngineErrorResponse($e);
            if ($proxyResponse instanceof JsonResponse) {
                return $proxyResponse;
            }

            Log::warning('ZoneAutomationStartCycleController: automation-engine request failed', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return $this->localizedError('upstream_error', 'Ошибка при запуске диагностики в automation-engine.', 503);
        } catch (ConnectionException $e) {
            Log::warning('ZoneAutomationStartCycleController: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return $this->localizedError('upstream_unavailable', null, 503);
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

    private function buildIdempotencyKey(int $zoneId): string
    {
        return Str::lower("zone-{$zoneId}-diagnostics-".Str::uuid());
    }
}
