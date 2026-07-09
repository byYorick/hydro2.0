<?php

namespace App\Services;

use App\Models\AutomationEffectiveBundle;
use App\Models\DeviceNode;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class NodeConfigService
{
    /**
     * Сформировать NodeConfig для отправки ноде.
     *
     * @param  array<int, array<string, mixed>>|null  $overrideChannels
     * @return array<string, mixed>
     */
    public function generateNodeConfig(
        DeviceNode $node,
        ?array $overrideChannels = null,
        bool $includeCredentials = false,
        bool $isNodeBinding = false
    ): array {
        $config = $this->getStoredConfig($node, $includeCredentials);

        if (empty($config)) {
            $config = [
                'node_id' => $node->uid,
                'version' => 1,
                'type' => $node->type,
                'channels' => [],
            ];
        }

        if ($overrideChannels !== null) {
            $config['channels'] = $overrideChannels;
        } elseif (! isset($config['channels']) || ! is_array($config['channels'])) {
            $config['channels'] = $this->buildChannelsFromNode($node);
        }

        $config['version'] = $config['version'] ?? 1;
        if ($includeCredentials) {
            $nodeSecret = $config['node_secret'] ?? null;
            if (! is_string($nodeSecret) || $nodeSecret === '') {
                $config['node_secret'] = config('app.node_default_secret') ?? config('app.key');
            }
        }

        $config = $this->mergeIrrigationFailSafeMirror($node, $config);

        return $config;
    }

    /**
     * Получить сохраненный NodeConfig из базы.
     *
     * @param  bool  $includeCredentials  Включать ли чувствительные данные (по умолчанию false)
     */
    public function getStoredConfig(DeviceNode $node, bool $includeCredentials = false): array
    {
        $config = is_array($node->config) ? $node->config : [];
        if (empty($config)) {
            return [];
        }

        return $this->sanitizeConfig($config, $includeCredentials);
    }

    private function sanitizeConfig(array $config, bool $includeCredentials): array
    {
        if (! $includeCredentials) {
            if (array_key_exists('wifi', $config)) {
                $config['wifi'] = ['configured' => true];
            }

            if (array_key_exists('mqtt', $config)) {
                $config['mqtt'] = ['configured' => true];
            }

            unset($config['node_secret']);
        } else {
            $nodeSecret = $config['node_secret'] ?? null;
            if (! is_string($nodeSecret) || $nodeSecret === '') {
                $config['node_secret'] = config('app.node_default_secret') ?? config('app.key');
            }
        }

        if (isset($config['channels']) && is_array($config['channels'])) {
            $config['channels'] = array_map(function ($entry) {
                return is_array($entry) ? $this->normalizeChannelForFirmware($entry) : $entry;
            }, $config['channels']);
        }

        return $config;
    }

    /**
     * @return array<int, array<string, mixed>>
     */
    private function buildChannelsFromNode(DeviceNode $node): array
    {
        $channels = $node->relationLoaded('channels') ? $node->channels : $node->channels()->get();
        $calibrationByChannelId = $this->activePumpCalibrationsByChannelId($channels->pluck('id')->all());

        return $channels->map(function ($channel) use ($calibrationByChannelId) {
            $base = [
                'name' => $channel->channel,
                'channel' => $channel->channel,
                'type' => $channel->type,
                'metric' => $channel->metric,
                'unit' => $channel->unit,
            ];
            $extra = is_array($channel->config) ? $channel->config : [];
            $merged = array_merge($extra, array_filter($base, static fn ($value) => $value !== null));
            $merged = $this->injectPumpCalibrationFirmwareFields(
                $merged,
                $calibrationByChannelId[(int) $channel->id] ?? null
            );

            return $this->normalizeChannelForFirmware($merged);
        })->values()->all();
    }

    /**
     * @param  list<int>  $channelIds
     * @return array<int, array{ml_per_sec: float, max_duration_ms: int|null}>
     */
    private function activePumpCalibrationsByChannelId(array $channelIds): array
    {
        if ($channelIds === [] || ! Schema::hasTable('pump_calibrations')) {
            return [];
        }

        $rows = DB::table('pump_calibrations as pc')
            ->whereIn('pc.node_channel_id', $channelIds)
            ->where('pc.is_active', true)
            ->where('pc.valid_from', '<=', now())
            ->where(function ($query): void {
                $query->whereNull('pc.valid_to')
                    ->orWhere('pc.valid_to', '>', now());
            })
            ->orderByDesc('pc.valid_from')
            ->orderByDesc('pc.id')
            ->get(['pc.node_channel_id', 'pc.ml_per_sec']);

        $result = [];
        foreach ($rows as $row) {
            $channelId = (int) $row->node_channel_id;
            if (array_key_exists($channelId, $result)) {
                continue;
            }
            $result[$channelId] = [
                'ml_per_sec' => (float) $row->ml_per_sec,
            ];
        }

        return $result;
    }

    /**
     * @param  array<string, mixed>  $channelConfig
     * @param  array{ml_per_sec: float}|null  $activeCalibration
     * @return array<string, mixed>
     */
    private function injectPumpCalibrationFirmwareFields(array $channelConfig, ?array $activeCalibration): array
    {
        if (strtoupper((string) ($channelConfig['type'] ?? '')) !== 'ACTUATOR') {
            return $channelConfig;
        }

        $mlPerSecond = $channelConfig['ml_per_second'] ?? null;
        if ((! is_numeric($mlPerSecond) || (float) $mlPerSecond <= 0) && $activeCalibration !== null) {
            $channelConfig['ml_per_second'] = (float) $activeCalibration['ml_per_sec'];
        }

        return $channelConfig;
    }

    private function normalizeChannelForFirmware(array $config): array
    {
        $config = $this->stripForbiddenChannelFields($config);

        $type = strtoupper((string) ($config['type'] ?? ''));
        $actuatorType = strtoupper((string) ($config['actuator_type'] ?? ''));

        if ($type === 'ACTUATOR' && in_array($actuatorType, ['RELAY', 'VALVE', 'FAN', 'HEATER'], true)) {
            $relayType = strtoupper((string) ($config['relay_type'] ?? ''));
            if (! in_array($relayType, ['NC', 'NO'], true)) {
                $config['relay_type'] = 'NO';
            }
        }

        return $config;
    }

    private function stripForbiddenChannelFields(array $config): array
    {
        unset($config['gpio'], $config['pin']);

        foreach ($config as $key => $value) {
            if (is_array($value)) {
                $config[$key] = $this->stripForbiddenChannelFields($value);
            }
        }

        return $config;
    }

    /**
     * @param  array<string, mixed>  $config
     * @return array<string, mixed>
     */
    private function mergeIrrigationFailSafeMirror(DeviceNode $node, array $config): array
    {
        $nodeType = strtolower(trim((string) ($node->type ?? $config['type'] ?? '')));
        if ($nodeType !== 'irrig') {
            return $config;
        }

        $zoneId = (int) ($node->zone_id ?: $node->pending_zone_id ?: 0);
        $failSafeGuards = $this->defaultIrrigationFailSafeGuards();

        if ($zoneId > 0) {
            $bundle = AutomationEffectiveBundle::query()
                ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
                ->where('scope_id', $zoneId)
                ->first();
            $bundleConfig = is_array($bundle?->config) ? $bundle->config : [];
            $activeProfile = data_get($bundleConfig, 'zone.logic_profile.active_profile');
            $activeProfile = is_array($activeProfile) && ! array_is_list($activeProfile) ? $activeProfile : [];
            $profileGuards = data_get($activeProfile, 'subsystems.diagnostics.execution.fail_safe_guards');
            $profileGuards = is_array($profileGuards) && ! array_is_list($profileGuards) ? $profileGuards : [];

            $irrigationSafety = data_get($activeProfile, 'subsystems.irrigation.safety');
            $irrigationSafety = is_array($irrigationSafety) && ! array_is_list($irrigationSafety) ? $irrigationSafety : [];

            $failSafeGuards['clean_fill_min_check_delay_ms'] = $this->toBoundedInt(
                $profileGuards['clean_fill_min_check_delay_ms'] ?? null,
                $failSafeGuards['clean_fill_min_check_delay_ms'],
                0,
                3600000
            );
            $failSafeGuards['solution_fill_clean_min_check_delay_ms'] = $this->toBoundedInt(
                $profileGuards['solution_fill_clean_min_check_delay_ms'] ?? null,
                $failSafeGuards['solution_fill_clean_min_check_delay_ms'],
                0,
                3600000
            );
            $failSafeGuards['solution_fill_solution_min_check_delay_ms'] = $this->toBoundedInt(
                $profileGuards['solution_fill_solution_min_check_delay_ms'] ?? null,
                $failSafeGuards['solution_fill_solution_min_check_delay_ms'],
                0,
                3600000
            );
            $failSafeGuards['recirculation_solution_min_guard_enabled'] = $this->toBool(
                $profileGuards['recirculation_stop_on_solution_min'] ?? null,
                $failSafeGuards['recirculation_solution_min_guard_enabled']
            );
            $failSafeGuards['irrigation_solution_min_guard_enabled'] = $this->toBool(
                $profileGuards['irrigation_stop_on_solution_min'] ?? $irrigationSafety['stop_on_solution_min'] ?? null,
                $failSafeGuards['irrigation_solution_min_guard_enabled']
            );
            $failSafeGuards['estop_debounce_ms'] = $this->toBoundedInt(
                $profileGuards['estop_debounce_ms'] ?? null,
                $failSafeGuards['estop_debounce_ms'],
                20,
                5000
            );
        }

        $config['fail_safe_guards'] = $failSafeGuards;

        return $config;
    }

    /**
     * @return array<string, mixed>
     */
    private function defaultIrrigationFailSafeGuards(): array
    {
        return [
            'clean_fill_min_check_delay_ms' => 5000,
            'solution_fill_clean_min_check_delay_ms' => 5000,
            'solution_fill_solution_min_check_delay_ms' => 60000,
            'recirculation_solution_min_guard_enabled' => true,
            'irrigation_solution_min_guard_enabled' => true,
            'estop_debounce_ms' => 80,
        ];
    }

    private function toBoundedInt(mixed $value, int $fallback, int $min, int $max): int
    {
        if (! is_numeric($value)) {
            return $fallback;
        }

        return max($min, min($max, (int) round((float) $value)));
    }

    private function toBool(mixed $value, bool $fallback): bool
    {
        if (is_bool($value)) {
            return $value;
        }

        if (is_numeric($value)) {
            return (int) $value !== 0;
        }

        if (is_string($value)) {
            $normalized = strtolower(trim($value));
            if (in_array($normalized, ['1', 'true', 'yes', 'on'], true)) {
                return true;
            }
            if (in_array($normalized, ['0', 'false', 'no', 'off'], true)) {
                return false;
            }
        }

        return $fallback;
    }
}
