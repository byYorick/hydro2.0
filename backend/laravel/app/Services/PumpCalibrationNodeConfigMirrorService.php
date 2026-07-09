<?php

namespace App\Services;

use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Support\PumpCalibrationCatalog;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class PumpCalibrationNodeConfigMirrorService
{
    private const ML_PER_SEC_EPSILON = 0.000001;

    /**
     * @return list<int> node_channel_id values that were synced
     */
    public function syncNodeActuatorChannels(DeviceNode $node, string $source = 'node_config_mirror'): array
    {
        $node->loadMissing('channels');

        $synced = [];
        foreach ($node->channels as $channel) {
            if ($this->syncActuatorChannel($channel, $source)) {
                $synced[] = (int) $channel->id;
            }
        }

        return $synced;
    }

    public function syncActuatorChannel(NodeChannel $channel, string $source = 'node_config_mirror'): bool
    {
        if (strtoupper(trim((string) ($channel->type ?? ''))) !== 'ACTUATOR') {
            return false;
        }

        $mlPerSecond = $this->extractMlPerSecond($channel->config);
        if ($mlPerSecond === null) {
            return false;
        }

        if (! Schema::hasTable('pump_calibrations')) {
            return false;
        }

        $active = DB::table('pump_calibrations')
            ->where('node_channel_id', $channel->id)
            ->where('is_active', true)
            ->where('valid_from', '<=', now())
            ->where(function ($query): void {
                $query->whereNull('valid_to')
                    ->orWhere('valid_to', '>', now());
            })
            ->orderByDesc('valid_from')
            ->orderByDesc('id')
            ->first();

        if ($active !== null) {
            $currentMlPerSec = (float) $active->ml_per_sec;
            if (abs($currentMlPerSec - $mlPerSecond) < self::ML_PER_SEC_EPSILON) {
                return false;
            }

            $this->insertCalibrationVersion(
                channel: $channel,
                mlPerSec: $mlPerSecond,
                component: is_string($active->component) && $active->component !== ''
                    ? (string) $active->component
                    : $this->resolveComponent($channel),
                source: $source,
                kMsPerMlL: $active->k_ms_per_ml_l !== null ? (float) $active->k_ms_per_ml_l : null,
                qualityScore: $active->quality_score !== null ? (float) $active->quality_score : null,
            );

            return true;
        }

        if (! $this->isDosingActuatorChannel($channel)) {
            return false;
        }

        $this->insertCalibrationVersion(
            channel: $channel,
            mlPerSec: $mlPerSecond,
            component: $this->resolveComponent($channel),
            source: $source,
        );

        return true;
    }

    private function insertCalibrationVersion(
        NodeChannel $channel,
        float $mlPerSec,
        string $component,
        string $source,
        ?float $kMsPerMlL = null,
        ?float $qualityScore = null,
    ): void {
        $now = now();

        DB::transaction(function () use ($channel, $mlPerSec, $component, $source, $kMsPerMlL, $qualityScore, $now): void {
            DB::table('pump_calibrations')
                ->where('node_channel_id', $channel->id)
                ->where('is_active', true)
                ->update([
                    'is_active' => false,
                    'valid_to' => $now,
                    'updated_at' => $now,
                ]);

            DB::table('pump_calibrations')->insert([
                'node_channel_id' => $channel->id,
                'component' => $component,
                'ml_per_sec' => $mlPerSec,
                'k_ms_per_ml_l' => $kMsPerMlL,
                'source' => $source,
                'quality_score' => $qualityScore,
                'sample_count' => 1,
                'valid_from' => $now,
                'is_active' => true,
                'meta' => json_encode([
                    'origin' => 'pump_calibration_node_config_mirror',
                    'node_channel_id' => $channel->id,
                    'node_id' => $channel->node_id,
                    'channel' => $channel->channel,
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'created_at' => $now,
                'updated_at' => $now,
            ]);
        });
    }

    private function extractMlPerSecond(mixed $config): ?float
    {
        if (! is_array($config)) {
            return null;
        }

        $candidates = [
            $config['ml_per_second'] ?? null,
            data_get($config, 'pump_calibration.ml_per_sec'),
        ];

        foreach ($candidates as $candidate) {
            if (! is_numeric($candidate)) {
                continue;
            }

            $value = (float) $candidate;
            if ($value > 0) {
                return round($value, 6);
            }
        }

        return null;
    }

    private function isDosingActuatorChannel(NodeChannel $channel): bool
    {
        $config = is_array($channel->config) ? $channel->config : [];
        $channelName = strtolower(trim((string) ($channel->channel ?? '')));
        $actuatorType = strtolower(trim((string) ($config['actuator_type'] ?? '')));

        if (PumpCalibrationCatalog::isDosingRole($channelName) || PumpCalibrationCatalog::isDosingRole($actuatorType)) {
            return true;
        }

        $component = data_get($config, 'pump_calibration.component');
        if (PumpCalibrationCatalog::isDosingComponent(is_string($component) ? $component : null)) {
            return true;
        }

        if (! DB::getSchemaBuilder()->hasTable('channel_bindings')) {
            return false;
        }

        return DB::table('channel_bindings')
            ->where('node_channel_id', $channel->id)
            ->whereIn('role', PumpCalibrationCatalog::dosingRoles())
            ->exists();
    }

    private function resolveComponent(NodeChannel $channel): string
    {
        $config = is_array($channel->config) ? $channel->config : [];
        $component = data_get($config, 'pump_calibration.component');
        if (PumpCalibrationCatalog::isDosingComponent(is_string($component) ? $component : null)) {
            return (string) $component;
        }

        $channelName = strtolower(trim((string) ($channel->channel ?? '')));
        if (PumpCalibrationCatalog::isDosingRole($channelName)) {
            return PumpCalibrationCatalog::componentForRole($channelName) ?? 'unknown';
        }

        if (DB::getSchemaBuilder()->hasTable('channel_bindings')) {
            $role = DB::table('channel_bindings')
                ->where('node_channel_id', $channel->id)
                ->whereIn('role', PumpCalibrationCatalog::dosingRoles())
                ->value('role');
            if (is_string($role) && $role !== '') {
                return PumpCalibrationCatalog::componentForRole($role) ?? 'unknown';
            }
        }

        return 'unknown';
    }
}
