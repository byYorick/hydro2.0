<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Services\AutomationRuntimeConfigService;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\Response;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;
use Illuminate\Validation\Rule;

class ZoneRelayAutotuneController extends Controller
{
    public function __construct(
        private readonly AutomationRuntimeConfigService $runtimeConfig,
    ) {
    }

    public function start(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $validated = $request->validate([
            'pid_type' => ['required', Rule::in(['ph', 'ec'])],
        ]);

        if (! $zone->activeGrowCycle()->exists()) {
            return response()->json([
                'status' => 'error',
                'message' => 'No active grow cycle in zone',
            ], 422);
        }

        try {
            $upstreamPayload = $this->startInAutomationEngine($zone->id, $validated['pid_type']);
        } catch (RequestException $e) {
            $proxyResponse = $this->buildUpstreamErrorResponse($e);
            if ($proxyResponse instanceof JsonResponse) {
                return $proxyResponse;
            }

            Log::warning('ZoneRelayAutotuneController: automation-engine request failed', [
                'zone_id' => $zone->id,
                'pid_type' => $validated['pid_type'],
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_UNAVAILABLE',
                'message' => 'Automation-engine недоступен.',
            ], 503);
        } catch (ConnectionException $e) {
            Log::warning('ZoneRelayAutotuneController: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'pid_type' => $validated['pid_type'],
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_UNAVAILABLE',
                'message' => 'Automation-engine недоступен.',
            ], 503);
        } catch (\Throwable $e) {
            Log::warning('ZoneRelayAutotuneController: unexpected upstream error', [
                'zone_id' => $zone->id,
                'pid_type' => $validated['pid_type'],
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_ERROR',
                'message' => 'Ошибка запуска relay-autotune.',
            ], 503);
        }

        ZoneEvent::create([
            'zone_id' => $zone->id,
            'type' => 'RELAY_AUTOTUNE_STARTED',
            'payload_json' => [
                'pid_type' => $validated['pid_type'],
            ],
        ]);

        return response()->json([
            'status' => 'ok',
            'data' => $upstreamPayload,
        ]);
    }

    public function status(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $validated = $request->validate([
            'pid_type' => ['nullable', Rule::in(['ph', 'ec'])],
        ]);
        $pidType = $validated['pid_type'] ?? 'ph';

        try {
            $upstreamPayload = $this->statusFromAutomationEngine($zone->id, $pidType);
            return response()->json([
                'status' => 'ok',
                'data' => $upstreamPayload,
            ]);
        } catch (RequestException $e) {
            $response = $e->response;
            if ($response instanceof Response && $response->status() === 404) {
                return response()->json([
                    'status' => 'ok',
                    'data' => $this->idlePayload($zone->id, $pidType),
                ]);
            }

            Log::info('ZoneRelayAutotuneController: upstream status unavailable, fallback idle', [
                'zone_id' => $zone->id,
                'pid_type' => $pidType,
                'error' => $e->getMessage(),
            ]);
        } catch (ConnectionException $e) {
            Log::info('ZoneRelayAutotuneController: connection failed, fallback idle', [
                'zone_id' => $zone->id,
                'pid_type' => $pidType,
                'error' => $e->getMessage(),
            ]);
        } catch (\Throwable $e) {
            Log::info('ZoneRelayAutotuneController: unexpected error, fallback idle', [
                'zone_id' => $zone->id,
                'pid_type' => $pidType,
                'error' => $e->getMessage(),
            ]);
        }

        return response()->json([
            'status' => 'ok',
            'data' => $this->idlePayload($zone->id, $pidType),
        ]);
    }

    /**
     * @return array<string,mixed>
     */
    private function startInAutomationEngine(int $zoneId, string $pidType): array
    {
        $cfg = $this->runtimeConfig->schedulerConfig();
        $apiUrl = (string) ($cfg['api_url'] ?? 'http://automation-engine:9405');
        $timeout = (float) ($cfg['timeout_sec'] ?? 2.0);

        /** @var Response $response */
        $response = Http::acceptJson()
            ->timeout($timeout)
            ->withHeaders($this->automationEngineHeaders())
            ->post("{$apiUrl}/zones/{$zoneId}/start-relay-autotune", [
                'pid_type' => $pidType,
            ]);

        $response->throw();

        $decoded = $response->json();
        if (! is_array($decoded)) {
            throw new \RuntimeException('automation_engine_invalid_payload');
        }

        return $decoded;
    }

    /**
     * @return array<string,mixed>
     */
    private function statusFromAutomationEngine(int $zoneId, string $pidType): array
    {
        $cfg = $this->runtimeConfig->schedulerConfig();
        $apiUrl = (string) ($cfg['api_url'] ?? 'http://automation-engine:9405');
        $timeout = (float) ($cfg['timeout_sec'] ?? 2.0);

        /** @var Response $response */
        $response = Http::acceptJson()
            ->timeout($timeout)
            ->withHeaders($this->automationEngineHeaders())
            ->get("{$apiUrl}/zones/{$zoneId}/relay-autotune/status", [
                'pid_type' => $pidType,
            ]);

        $response->throw();

        $decoded = $response->json();
        if (! is_array($decoded)) {
            throw new \RuntimeException('automation_engine_invalid_payload');
        }

        return $decoded;
    }

    private function buildUpstreamErrorResponse(RequestException $e): ?JsonResponse
    {
        $response = $e->response;
        if (! $response instanceof Response) {
            return null;
        }

        $status = $response->status();
        if ($status < 400 || $status >= 500) {
            return null;
        }

        if ($status === 404) {
            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_NOT_SUPPORTED',
                'message' => 'Automation-engine ещё не поддерживает relay-autotune API.',
            ], 501);
        }

        $decoded = $response->json();
        if (is_array($decoded)) {
            return response()->json($decoded, $status);
        }

        return response()->json([
            'status' => 'error',
            'code' => 'UPSTREAM_ERROR',
            'message' => 'Ошибка upstream сервиса automation-engine.',
        ], $status);
    }

    /**
     * @return array<string,mixed>
     */
    private function idlePayload(int $zoneId, string $pidType): array
    {
        return [
            'zone_id' => $zoneId,
            'pid_type' => $pidType,
            'status' => 'idle',
        ];
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
     * @return array<string,string>
     */
    private function automationEngineHeaders(): array
    {
        $cfg = $this->runtimeConfig->schedulerConfig();

        $headers = [
            'X-Trace-Id' => Str::lower((string) Str::uuid()),
            'X-Scheduler-Id' => (string) ($cfg['scheduler_id'] ?? 'laravel-api'),
        ];

        $token = trim((string) ($cfg['token'] ?? ''));
        if ($token !== '') {
            $headers['Authorization'] = 'Bearer '.$token;
        }

        return $headers;
    }
}
