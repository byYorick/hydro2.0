<?php

namespace App\Services;

use App\Models\ChannelBinding;
use App\Models\Sensor;
use App\Models\Zone;
use Illuminate\Support\Facades\Log;

class SoilMoistureSensorBindingService
{
    public function provisionSensorForBinding(ChannelBinding $binding): void
    {
        $role = strtolower((string) ($binding->role ?? ''));
        if ($role !== 'soil_moisture_sensor') {
            return;
        }

        $binding->loadMissing(['nodeChannel.node']);

        $node = $binding->nodeChannel?->node;
        if (! $node) {
            Log::warning('SoilMoistureSensorBindingService: node missing for binding', [
                'binding_id' => $binding->id,
                'node_channel_id' => $binding->node_channel_id,
            ]);

            return;
        }

        $zoneId = $node->zone_id ? (int) $node->zone_id : null;
        if (! $zoneId) {
            // Важно: AE читает sensors по zone_id. Если нода ещё не подтверждена в зоне (pending bind),
            // сенсор создавать рано — он будет "в никуда" и не будет найден AE.
            Log::info('SoilMoistureSensorBindingService: skip provisioning; node has no stable zone_id', [
                'binding_id' => $binding->id,
                'node_id' => $node->id,
                'node_uid' => $node->uid,
            ]);

            return;
        }

        $zone = Zone::query()->select(['id', 'greenhouse_id'])->find($zoneId);
        if (! $zone) {
            Log::warning('SoilMoistureSensorBindingService: zone not found for node', [
                'binding_id' => $binding->id,
                'node_id' => $node->id,
                'zone_id' => $zoneId,
            ]);

            return;
        }

        $channelLabel = (string) ($binding->nodeChannel?->channel ?? '');
        $channelLabel = trim($channelLabel) !== '' ? $channelLabel : 'soil_moisture';

        $unit = (string) ($binding->nodeChannel?->unit ?? '');
        $unit = trim($unit) !== '' ? $unit : null;

        Sensor::query()->updateOrCreate(
            [
                'zone_id' => $zoneId,
                'node_id' => (int) $node->id,
                'scope' => 'inside',
                'type' => 'SOIL_MOISTURE',
                'label' => $channelLabel,
            ],
            [
                'greenhouse_id' => (int) $zone->greenhouse_id,
                'unit' => $unit,
                'is_active' => true,
                'specs' => [
                    'source' => 'binding_role',
                    'binding_role' => 'soil_moisture_sensor',
                    'channel_binding_id' => (int) $binding->id,
                    'node_channel_id' => (int) ($binding->node_channel_id ?? 0),
                ],
            ]
        );
    }
}

