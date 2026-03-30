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
