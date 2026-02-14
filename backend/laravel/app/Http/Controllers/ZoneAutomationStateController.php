<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\Response;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class ZoneAutomationStateController extends Controller
{
    public function show(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        try {
            $payload = $this->fetchAutomationStateFromAutomationEngine($zone->id);
        } catch (ConnectionException|RequestException $e) {
            Log::warning('ZoneAutomationStateController: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_UNAVAILABLE',
                'message' => 'Automation-engine недоступен.',
            ], 503);
        } catch (\Throwable $e) {
            Log::warning('ZoneAutomationStateController: unexpected upstream error', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_ERROR',
                'message' => 'Ошибка при получении состояния автоматизации.',
            ], 503);
        }

        return response()->json($payload);
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

    /**
     * @return array<string,mixed>
     */
    private function fetchAutomationStateFromAutomationEngine(int $zoneId): array
    {
        $apiUrl = rtrim((string) config('services.automation_engine.api_url', 'http://automation-engine:9405'), '/');
        $timeout = (float) config('services.automation_engine.timeout', 2.0);

        /** @var Response $response */
        $response = Http::acceptJson()
            ->timeout($timeout)
            ->get("{$apiUrl}/zones/{$zoneId}/automation-state");

        $response->throw();

        $payload = $response->json();
        if (! is_array($payload)) {
            throw new \RuntimeException('automation_engine_invalid_payload');
        }

        if (! array_key_exists('zone_id', $payload)) {
            $payload['zone_id'] = $zoneId;
        }

        return $payload;
    }
}
