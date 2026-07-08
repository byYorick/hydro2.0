<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Services\Ae3IrrigationBridgeService;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class ZoneAutomationStartSolutionTopupController extends Controller
{
    use Concerns\PresentsLocalizedApiErrors;

    public function __construct(
        private readonly Ae3IrrigationBridgeService $bridge,
    ) {}

    public function store(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $validated = $request->validate([
            'mode' => ['nullable', 'string', 'in:normal,force'],
            'source' => ['nullable', 'string', 'max:64'],
            'trigger' => ['nullable', 'string', 'max:32'],
            'idempotency_key' => ['nullable', 'string', 'min:8', 'max:160'],
        ]);

        $payload = [
            'mode' => $validated['mode'] ?? 'normal',
            'source' => $validated['source'] ?? 'laravel_api',
            'trigger' => $validated['trigger'] ?? 'manual',
            'idempotency_key' => $validated['idempotency_key'] ?? $this->buildIdempotencyKey(
                zoneId: $zone->id,
                mode: $validated['mode'] ?? 'normal',
            ),
        ];

        try {
            return response()->json($this->bridge->dispatchStartSolutionTopup($zone->id, $payload));
        } catch (RequestException $e) {
            $proxyResponse = $this->buildAutomationEngineErrorResponse($e);
            if ($proxyResponse instanceof JsonResponse) {
                return $proxyResponse;
            }

            Log::warning('ZoneAutomationStartSolutionTopupController: automation-engine request failed', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return $this->localizedError('upstream_error', 'Ошибка при запуске автодолива в automation-engine.', 503);
        } catch (ConnectionException $e) {
            Log::warning('ZoneAutomationStartSolutionTopupController: automation-engine unavailable', [
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

    private function buildIdempotencyKey(int $zoneId, string $mode): string
    {
        return Str::lower("zone-{$zoneId}-solution-topup-{$mode}-".Str::uuid());
    }
}
