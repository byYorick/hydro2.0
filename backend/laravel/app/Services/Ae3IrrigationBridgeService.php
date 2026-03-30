<?php

namespace App\Services;

use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\Response;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;

class Ae3IrrigationBridgeService
{
    public function __construct(
        private readonly AutomationRuntimeConfigService $runtimeConfig,
        private readonly ZoneAutomationIntentService $intentService,
    ) {
    }

    /**
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>
     *
     * @throws ConnectionException
     * @throws RequestException
     */
    public function startIrrigation(int $zoneId, array $payload): array
    {
        $cfg = $this->runtimeConfig->schedulerConfig();
        $apiUrl = (string) ($cfg['api_url'] ?? 'http://automation-engine:9405');
        $timeout = (float) ($cfg['timeout_sec'] ?? 2.0);

        /** @var Response $response */
        $response = Http::acceptJson()
            ->timeout($timeout)
            ->withHeaders($this->automationEngineHeaders())
            ->post("{$apiUrl}/zones/{$zoneId}/start-irrigation", $payload);

        $response->throw();

        $decoded = $response->json();
        if (! is_array($decoded)) {
            throw new \RuntimeException('automation_engine_invalid_payload');
        }

        return $decoded;
    }

    /**
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>
     *
     * @throws ConnectionException
     * @throws RequestException
     */
    public function dispatchStartIrrigation(
        int $zoneId,
        array $payload,
    ): array {
        $mode = ($payload['mode'] ?? null) === 'force' ? 'force' : 'normal';
        $source = trim((string) ($payload['source'] ?? 'laravel_api'));
        $idempotencyKey = trim((string) ($payload['idempotency_key'] ?? ''));
        $requestedDurationSec = isset($payload['requested_duration_sec']) && is_numeric($payload['requested_duration_sec'])
            ? max(1, (int) $payload['requested_duration_sec'])
            : null;

        $normalizedPayload = [
            'mode' => $mode,
            'source' => $source !== '' ? $source : 'laravel_api',
            'requested_duration_sec' => $requestedDurationSec,
            'idempotency_key' => $idempotencyKey,
        ];

        $this->intentService->upsertStartIrrigationIntent(
            zoneId: $zoneId,
            source: $normalizedPayload['source'],
            idempotencyKey: $idempotencyKey,
            mode: $mode,
            requestedDurationSec: $requestedDurationSec,
        );

        try {
            return $this->startIrrigation($zoneId, $normalizedPayload);
        } catch (RequestException $e) {
            $this->intentService->markIntentFailed(
                zoneId: $zoneId,
                idempotencyKey: $idempotencyKey,
                errorCode: 'automation_engine_start_irrigation_http_error',
                errorMessage: $e->getMessage(),
            );

            throw $e;
        } catch (ConnectionException $e) {
            $this->intentService->markIntentFailed(
                zoneId: $zoneId,
                idempotencyKey: $idempotencyKey,
                errorCode: 'automation_engine_start_irrigation_connection_error',
                errorMessage: $e->getMessage(),
            );

            throw $e;
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
