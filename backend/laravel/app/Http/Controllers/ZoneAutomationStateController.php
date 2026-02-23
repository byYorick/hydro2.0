<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\Response;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class ZoneAutomationStateController extends Controller
{
    private const STATE_CACHE_TTL_SECONDS = 300;

    public function show(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        try {
            $payload = $this->fetchAutomationStateFromAutomationEngine($zone->id);
            $this->cacheState($zone->id, $payload);

            return response()->json($this->decorateStatePayload($payload, false, 'live'));
        } catch (ConnectionException|RequestException $e) {
            Log::warning('ZoneAutomationStateController: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            $cachedPayload = $this->getCachedState($zone->id);
            if ($cachedPayload !== null) {
                Log::info('ZoneAutomationStateController: returning cached state snapshot', [
                    'zone_id' => $zone->id,
                    'source' => 'cache',
                    'reason' => 'upstream_unavailable',
                ]);

                return response()->json($this->decorateStatePayload($cachedPayload, true, 'cache'));
            }

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

            $cachedPayload = $this->getCachedState($zone->id);
            if ($cachedPayload !== null) {
                Log::info('ZoneAutomationStateController: returning cached state snapshot', [
                    'zone_id' => $zone->id,
                    'source' => 'cache',
                    'reason' => 'unexpected_upstream_error',
                ]);

                return response()->json($this->decorateStatePayload($cachedPayload, true, 'cache'));
            }

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_ERROR',
                'message' => 'Ошибка при получении состояния автоматизации.',
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
            ->retry(2, 150, function ($exception) {
                return $exception instanceof ConnectionException;
            })
            ->get("{$apiUrl}/zones/{$zoneId}/state");

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

    /**
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>
     */
    private function decorateStatePayload(array $payload, bool $isStale, string $source): array
    {
        $payload['state_meta'] = [
            'source' => $source,
            'is_stale' => $isStale,
            'served_at' => now()->toIso8601String(),
        ];

        return $payload;
    }

    /**
     * @param  array<string,mixed>  $payload
     */
    private function cacheState(int $zoneId, array $payload): void
    {
        Cache::put(
            $this->stateCacheKey($zoneId),
            $payload,
            now()->addSeconds(self::STATE_CACHE_TTL_SECONDS)
        );
    }

    /**
     * @return array<string,mixed>|null
     */
    private function getCachedState(int $zoneId): ?array
    {
        $cached = Cache::get($this->stateCacheKey($zoneId));
        if (! is_array($cached)) {
            return null;
        }

        return $cached;
    }

    private function stateCacheKey(int $zoneId): string
    {
        return "zone_automation_state:{$zoneId}";
    }
}
