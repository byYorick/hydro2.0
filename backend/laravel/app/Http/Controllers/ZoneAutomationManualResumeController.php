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

class ZoneAutomationManualResumeController extends Controller
{
    public function store(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $validated = $request->validate([
            'task_id' => ['nullable', 'string', 'regex:/^st-[A-Za-z0-9\-_.:]{6,128}$/'],
            'source' => ['nullable', 'string', 'max:64'],
        ]);

        $payload = array_filter([
            'task_id' => $validated['task_id'] ?? null,
            'source' => $validated['source'] ?? 'frontend_manual_resume',
        ], static fn ($value): bool => $value !== null && $value !== '');

        try {
            $upstreamPayload = $this->forwardManualResume($zone->id, $payload);
        } catch (ConnectionException|RequestException $e) {
            $status = $e instanceof RequestException && $e->response instanceof Response
                ? $e->response->status()
                : null;

            if ($status === 404) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'UPSTREAM_NOT_SUPPORTED',
                    'message' => 'Automation-engine ещё не поддерживает manual_resume.',
                ], 501);
            }

            Log::warning('ZoneAutomationManualResumeController: automation-engine unavailable', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
                'status' => $status,
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_UNAVAILABLE',
                'message' => 'Automation-engine недоступен.',
            ], 503);
        } catch (\Throwable $e) {
            Log::warning('ZoneAutomationManualResumeController: unexpected upstream error', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_ERROR',
                'message' => 'Ошибка при запросе manual_resume.',
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
    private function forwardManualResume(int $zoneId, array $payload): array
    {
        $apiUrl = rtrim((string) config('services.automation_engine.api_url', 'http://automation-engine:9405'), '/');
        $timeout = (float) config('services.automation_engine.timeout', 2.0);

        /** @var Response $response */
        $response = Http::acceptJson()
            ->timeout($timeout)
            ->post("{$apiUrl}/zones/{$zoneId}/automation/manual-resume", $payload);

        $response->throw();

        $decoded = $response->json();
        if (! is_array($decoded)) {
            throw new \RuntimeException('automation_engine_invalid_payload');
        }

        return $decoded;
    }
}
