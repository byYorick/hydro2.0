<?php

namespace App\Services;

use App\Models\NodeChannel;
use App\Models\SensorCalibration;
use App\Models\Zone;
use DomainException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;

class SensorCalibrationCommandService
{
    public function submitPoint(
        SensorCalibration $calibration,
        NodeChannel $channel,
        Zone $zone,
        int $stage,
        float $referenceValue,
    ): SensorCalibration {
        $channel->loadMissing('node');
        $node = $channel->node;
        if (! $node) {
            throw new \RuntimeException("node_channel {$channel->id} has no node");
        }
        if ($node->status !== 'online') {
            throw new DomainException("Node {$node->uid} is offline; sensor calibration command cannot be sent.");
        }

        $commandId = (string) Str::uuid();
        $response = Http::baseUrl($this->historyLoggerBaseUrl())
            ->withToken($this->historyLoggerToken())
            ->acceptJson()
            ->post('/commands', $this->buildPayload(
                calibration: $calibration,
                zone: $zone,
                channel: $channel,
                stage: $stage,
                referenceValue: $referenceValue,
                commandId: $commandId,
            ));

        $response->throw();

        $now = now();
        if ($stage === 1) {
            $calibration->fill([
                'point_1_reference' => $referenceValue,
                'point_1_command_id' => $commandId,
                'point_1_sent_at' => $now,
                'point_1_result' => null,
                'point_1_error' => null,
                'status' => SensorCalibration::STATUS_POINT_1_PENDING,
            ]);
        } else {
            $meta = is_array($calibration->meta) ? $calibration->meta : [];
            unset($meta['awaiting_config_report'], $meta['persisted_via_config_report'], $meta['persisted_at']);
            $calibration->fill([
                'point_2_reference' => $referenceValue,
                'point_2_command_id' => $commandId,
                'point_2_sent_at' => $now,
                'point_2_result' => null,
                'point_2_error' => null,
                'status' => SensorCalibration::STATUS_POINT_2_PENDING,
                'meta' => $meta,
            ]);
        }

        $calibration->save();

        return $calibration->fresh(['nodeChannel.node']);
    }

    public function sensorSettings(): array
    {
        return app(AutomationConfigDocumentService::class)->getSystemPayloadByLegacyNamespace('sensor_calibration', true);
    }

    private function buildPayload(
        SensorCalibration $calibration,
        Zone $zone,
        NodeChannel $channel,
        int $stage,
        float $referenceValue,
        string $commandId,
    ): array {
        $channel->loadMissing('node');
        $node = $channel->node;
        if (! $node) {
            throw new \RuntimeException("node_channel {$channel->id} has no node");
        }

        $params = ['stage' => $stage];
        if ($calibration->sensor_type === 'ph') {
            $params['known_ph'] = $referenceValue;
        } else {
            $params['tds_value'] = (int) round($referenceValue);
        }

        return [
            'greenhouse_uid' => optional($zone->greenhouse)->uid ?? 'gh-1',
            'zone_id' => $zone->id,
            'zone_uid' => $zone->uid,
            'node_uid' => $node->uid,
            'channel' => $channel->channel,
            'cmd' => 'calibrate',
            'params' => $params,
            'source' => 'api',
            'cmd_id' => $commandId,
        ];
    }

    private function historyLoggerBaseUrl(): string
    {
        $url = (string) Config::get('services.history_logger.url', '');
        if ($url === '') {
            throw new \RuntimeException('History Logger URL not configured');
        }

        return rtrim($url, '/');
    }

    private function historyLoggerToken(): ?string
    {
        return Config::get('services.history_logger.token') ?? Config::get('services.python_bridge.token');
    }
}
