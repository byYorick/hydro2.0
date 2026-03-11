<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Services\AutomationRuntimeConfigService;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\Response;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class ZoneAutomationManualStepController extends Controller
{
    public function __construct(
        private readonly AutomationRuntimeConfigService $runtimeConfig,
    ) {
    }

    public function store(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $validated = $request->validate([
            'manual_step' => ['required', 'string', 'in:clean_fill_start,clean_fill_stop,solution_fill_start,solution_fill_stop,prepare_recirculation_start,prepare_recirculation_stop,irrigation_recovery_start,irrigation_recovery_stop'],
            'source' => ['nullable', 'string', 'max:64'],
        ]);

        $payload = [
            'manual_step' => $validated['manual_step'],
            'source' => $validated['source'] ?? 'frontend_manual_step',
        ];

        try {
            $upstreamPayload = $this->forwardManualStep($zone->id, $payload);
        } catch (RequestException $e) {
            $proxyResponse = $this->buildUpstreamErrorResponse($e);
            if ($proxyResponse instanceof JsonResponse) {
                return $proxyResponse;
            }

            Log::warning('ZoneAutomationManualStepController: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_UNAVAILABLE',
                'message' => 'Automation-engine недоступен.',
            ], 503);
        } catch (ConnectionException $e) {
            Log::warning('ZoneAutomationManualStepController: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_UNAVAILABLE',
                'message' => 'Automation-engine недоступен.',
            ], 503);
        } catch (\Throwable $e) {
            Log::warning('ZoneAutomationManualStepController: unexpected upstream error', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_ERROR',
                'message' => 'Ошибка при запуске manual step.',
            ], 503);
        }

        return response()->json($upstreamPayload);
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
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>
     */
    private function forwardManualStep(int $zoneId, array $payload): array
    {
        $cfg = $this->runtimeConfig->schedulerConfig();
        $apiUrl = (string) ($cfg['api_url'] ?? 'http://automation-engine:9405');
        $timeout = (float) ($cfg['timeout_sec'] ?? 2.0);

        /** @var Response $response */
        $response = Http::acceptJson()
            ->timeout($timeout)
            ->withHeaders($this->automationEngineHeaders())
            ->post("{$apiUrl}/zones/{$zoneId}/manual-step", $payload);

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

        $decoded = $response->json();
        if (is_array($decoded)) {
            if ($status === 404) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'UPSTREAM_NOT_SUPPORTED',
                    'message' => 'Automation-engine ещё не поддерживает manual-step API.',
                ], 501);
            }

            return response()->json($decoded, $status);
        }

        return response()->json([
            'status' => 'error',
            'code' => 'UPSTREAM_ERROR',
            'message' => 'Ошибка upstream сервиса automation-engine.',
        ], $status);
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
