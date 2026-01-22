<?php

namespace App\Jobs;

use App\Models\DeviceNode;
use App\Models\ZoneSimulation;
use App\Services\NodeSimManagerClient;
use App\Services\PythonBridgeService;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Log;

class StopSimulationNodesJob implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $timeout = 60;

    /**
     * Create a new job instance.
     */
    public function __construct(
        public int $zoneId,
        public ?int $simulationId = null,
        public ?string $jobId = null
    ) {
        //
    }

    /**
     * Execute the job.
     */
    public function handle(PythonBridgeService $bridge, NodeSimManagerClient $nodeSimManager): void
    {
        $sessionId = null;
        if ($this->simulationId) {
            $simulation = ZoneSimulation::find($this->simulationId);
            if (! $simulation) {
                return;
            }
            $scenario = $simulation->scenario ?? [];
            if (! isset($scenario['simulation']) || ! is_array($scenario['simulation'])) {
                return;
            }
            $sessionId = $scenario['simulation']['node_sim_session_id'] ?? null;
        }

        $nodes = DeviceNode::query()
            ->where('zone_id', $this->zoneId)
            ->where('status', 'online')
            ->with(['channels' => function ($query) {
                $query->where('type', 'ACTUATOR');
            }])
            ->get();

        if ($nodes->isEmpty()) {
            Log::info('StopSimulationNodesJob: no nodes to stop', [
                'zone_id' => $this->zoneId,
                'simulation_id' => $this->simulationId,
                'job_id' => $this->jobId,
            ]);

            if ($sessionId) {
                try {
                    $nodeSimManager->stopSession($sessionId);
                } catch (\Throwable $e) {
                    Log::warning('StopSimulationNodesJob: failed to stop node-sim session', [
                        'zone_id' => $this->zoneId,
                        'simulation_id' => $this->simulationId,
                        'job_id' => $this->jobId,
                        'session_id' => $sessionId,
                        'error' => $e->getMessage(),
                    ]);
                }
            }

            return;
        }

        foreach ($nodes as $node) {
            foreach ($node->channels as $channel) {
                $channelName = $channel->channel;
                $config = is_array($channel->config) ? $channel->config : [];
                $actuatorType = strtoupper((string) ($config['actuator_type'] ?? ''));
                $isPwm = $actuatorType === 'PWM' || str_contains(strtolower($channelName), 'pwm');

                $payload = $isPwm
                    ? [
                        'type' => 'set_pwm',
                        'channel' => $channelName,
                        'params' => [
                            'value' => 0,
                        ],
                    ]
                    : [
                        'type' => 'set_relay',
                        'channel' => $channelName,
                        'params' => [
                            'state' => false,
                        ],
                    ];

                try {
                    $bridge->sendNodeCommand($node, $payload);
                } catch (\Throwable $e) {
                    Log::warning('StopSimulationNodesJob: failed to send stop command', [
                        'zone_id' => $this->zoneId,
                        'node_uid' => $node->uid,
                        'channel' => $channelName,
                        'command' => $payload['type'],
                        'error' => $e->getMessage(),
                    ]);
                }
            }
        }

        if ($sessionId) {
            try {
                $nodeSimManager->stopSession($sessionId);
            } catch (\Throwable $e) {
                Log::warning('StopSimulationNodesJob: failed to stop node-sim session', [
                    'zone_id' => $this->zoneId,
                    'simulation_id' => $this->simulationId,
                    'job_id' => $this->jobId,
                    'session_id' => $sessionId,
                    'error' => $e->getMessage(),
                ]);
            }
        }
    }
}
