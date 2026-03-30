<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Services\Ae3IrrigationBridgeService;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\Response;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class ZoneAutomationStartIrrigationController extends Controller
{
    public function __construct(
        private readonly Ae3IrrigationBridgeService $bridge,
    ) {
    }

    public function store(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $validated = $request->validate([
            'mode' => ['nullable', 'string', 'in:normal,force'],
            'source' => ['nullable', 'string', 'max:64'],
            'requested_duration_sec' => ['nullable', 'integer', 'min:1', 'max:3600'],
            'idempotency_key' => ['nullable', 'string', 'min:8', 'max:160'],
        ]);

        $payload = [
            'mode' => $validated['mode'] ?? 'normal',
            'source' => $validated['source'] ?? 'laravel_api',
            'requested_duration_sec' => $validated['requested_duration_sec'] ?? null,
            'idempotency_key' => $validated['idempotency_key'] ?? $this->buildIdempotencyKey(
                zoneId: $zone->id,
                mode: $validated['mode'] ?? 'normal',
            ),
        ];

        try {
            return response()->json($this->bridge->dispatchStartIrrigation($zone->id, $payload));
        } catch (RequestException $e) {
            $proxyResponse = $this->buildUpstreamErrorResponse($e);
            if ($proxyResponse instanceof JsonResponse) {
                return $proxyResponse;
            }

            Log::warning('ZoneAutomationStartIrrigationController: automation-engine request failed', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_ERROR',
                'message' => 'Ошибка при запуске полива в automation-engine.',
            ], 503);
        } catch (ConnectionException $e) {
            Log::warning('ZoneAutomationStartIrrigationController: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_UNAVAILABLE',
                'message' => 'Automation-engine недоступен.',
            ], 503);
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
        return Str::lower("zone-{$zoneId}-irrigation-{$mode}-".Str::uuid());
    }

    private function buildUpstreamErrorResponse(RequestException $e): ?JsonResponse
    {
        $response = $e->response;
        if (! $response instanceof Response) {
            return null;
        }

        $decoded = $response->json();
        if (is_array($decoded)) {
            return response()->json($decoded, $response->status());
        }

        return response()->json([
            'status' => 'error',
            'code' => 'UPSTREAM_ERROR',
            'message' => 'Ошибка upstream сервиса automation-engine.',
        ], $response->status());
    }
}
