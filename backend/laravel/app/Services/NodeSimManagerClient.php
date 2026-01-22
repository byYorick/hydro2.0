<?php

namespace App\Services;

use App\Models\Zone;
use App\Models\ZoneSimulation;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class NodeSimManagerClient
{
    /**
     * @param  array{host:string,port:int,username:?string,password:?string,tls:bool,ca_certs:?string,keepalive:int}  $mqttDefaults
     * @param  array{interval_seconds:float,heartbeat_interval_seconds:float,status_interval_seconds:float}  $telemetryDefaults
     */
    public function __construct(
        private string $baseUrl,
        private ?string $token,
        private int $timeoutSeconds,
        private array $mqttDefaults,
        private array $telemetryDefaults,
    ) {}

    public function startSession(ZoneSimulation $simulation, string $sessionId): void
    {
        $zone = Zone::query()
            ->with(['greenhouse', 'nodes.channels'])
            ->findOrFail($simulation->zone_id);

        $nodes = $this->buildNodeConfigs($zone);
        if (empty($nodes)) {
            throw new \RuntimeException('No nodes available for node-sim session.');
        }

        $payload = [
            'session_id' => $sessionId,
            'simulation_id' => $simulation->id,
            'zone_id' => $zone->id,
            'zone_uid' => $zone->uid,
            'mqtt' => $this->mqttDefaults,
            'telemetry' => $this->telemetryDefaults,
            'nodes' => $nodes,
        ];

        $this->sendRequest('/sessions/start', $payload);
    }

    public function stopSession(string $sessionId): void
    {
        $payload = [
            'session_id' => $sessionId,
        ];

        $this->sendRequest('/sessions/stop', $payload);
    }

    /**
     * @return array<int, array<string, mixed>>
     */
    private function buildNodeConfigs(Zone $zone): array
    {
        $ghUid = $zone->greenhouse?->uid ?? 'gh-1';
        $zoneUid = $zone->uid ?? ('zn-'.$zone->id);

        return $zone->nodes
            ->map(function ($node) use ($ghUid, $zoneUid) {
                $channels = $node->channels ?? collect();
                $sensorChannels = $channels
                    ->filter(fn ($channel) => strtoupper((string) $channel->type) !== 'ACTUATOR')
                    ->pluck('channel')
                    ->filter()
                    ->values()
                    ->all();
                $actuatorChannels = $channels
                    ->filter(fn ($channel) => strtoupper((string) $channel->type) === 'ACTUATOR')
                    ->pluck('channel')
                    ->filter()
                    ->values()
                    ->all();

                return [
                    'node_uid' => $node->uid,
                    'hardware_id' => $node->hardware_id,
                    'gh_uid' => $ghUid,
                    'zone_uid' => $zoneUid,
                    'node_type' => $this->normalizeNodeType($node->type),
                    'mode' => 'configured',
                    'config_report_on_start' => true,
                    'sensors' => $sensorChannels,
                    'actuators' => $actuatorChannels,
                ];
            })
            ->filter(fn ($node) => ! empty($node['node_uid']) && ! empty($node['hardware_id']))
            ->values()
            ->all();
    }

    private function normalizeNodeType(?string $nodeType): string
    {
        $normalized = strtolower((string) $nodeType);
        $allowed = ['ph', 'ec', 'climate', 'pump', 'irrig', 'light', 'unknown'];

        if (! in_array($normalized, $allowed, true)) {
            return 'unknown';
        }

        return $normalized;
    }

    private function sendRequest(string $path, array $payload): void
    {
        $url = rtrim($this->baseUrl, '/').$path;
        $headers = $this->token ? ['Authorization' => "Bearer {$this->token}"] : [];

        $response = Http::withHeaders($headers)
            ->timeout($this->timeoutSeconds)
            ->post($url, $payload);

        if ($response->successful()) {
            return;
        }

        Log::warning('Node-sim manager request failed', [
            'url' => $url,
            'status' => $response->status(),
            'body' => $response->body(),
        ]);

        throw new \RuntimeException('Node-sim manager request failed: '.$response->body());
    }
}
