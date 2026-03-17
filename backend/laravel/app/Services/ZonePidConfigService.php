<?php

namespace App\Services;

use App\Models\SystemAutomationSetting;
use App\Models\ZoneEvent;
use App\Models\ZonePidConfig;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class ZonePidConfigService
{
    /**
     * @return array<string, mixed>
     */
    public function serializeConfig(ZonePidConfig $config): array
    {
        return [
            'id' => $config->id,
            'zone_id' => $config->zone_id,
            'type' => $config->type,
            'config' => $config->config ?? [],
            'updated_by' => $config->updated_by,
            'updated_at' => optional($config->updated_at)->toISOString(),
            'is_default' => false,
        ];
    }

    /**
     * Получить конфиг PID для зоны и типа
     */
    public function getConfig(int $zoneId, string $type): ?ZonePidConfig
    {
        return ZonePidConfig::where('zone_id', $zoneId)
            ->where('type', $type)
            ->first();
    }

    /**
     * Создать или обновить конфиг PID
     */
    public function createOrUpdate(int $zoneId, string $type, array $config, ?int $userId = null): ZonePidConfig
    {
        return DB::transaction(function () use ($zoneId, $type, $config, $userId) {
            $existing = $this->getConfig($zoneId, $type);
            $oldConfig = $existing ? $existing->config : null;

            if ($existing) {
                // Обновляем существующий конфиг
                $existing->config = $config;
                $existing->updated_by = $userId;
                $existing->updated_at = now();
                $existing->save();
                $pidConfig = $existing->fresh();
            } else {
                // Создаем новый конфиг
                $pidConfig = ZonePidConfig::create([
                    'zone_id' => $zoneId,
                    'type' => $type,
                    'config' => $config,
                    'updated_by' => $userId,
                ]);
            }

            // Создаем событие об обновлении конфига
            ZoneEvent::create([
                'zone_id' => $zoneId,
                'type' => 'PID_CONFIG_UPDATED',
                'payload_json' => [
                    'type' => $type,
                    'old_config' => $oldConfig,
                    'new_config' => $config,
                    'updated_by' => $userId,
                ],
            ]);

            Log::info('PID config updated', [
                'zone_id' => $zoneId,
                'type' => $type,
                'updated_by' => $userId,
            ]);

            return $pidConfig;
        });
    }

    /**
     * Получить дефолтный конфиг для типа
     * Значения берутся из system_automation_settings с fallback на встроенные каталожные defaults.
     */
    public function getDefaultConfig(string $type): array
    {
        $namespace = $this->defaultNamespace($type);

        try {
            $config = SystemAutomationSetting::forNamespace($namespace);
        } catch (\RuntimeException) {
            return $this->catalogDefaultConfig($type);
        }

        if (! $this->isValidDefaultConfig($config)) {
            Log::warning('PID default config is invalid, falling back to catalog defaults', [
                'namespace' => $namespace,
            ]);

            return $this->catalogDefaultConfig($type);
        }

        return $config;
    }

    /**
     * Дополнительная валидация конфига
     */
    public function validateConfig(array $config, string $type): void
    {
        // Проверка, что close_zone > dead_zone
        if ($config['close_zone'] <= $config['dead_zone']) {
            throw new \InvalidArgumentException('close_zone должна быть больше dead_zone');
        }

        // Проверка, что far_zone > close_zone
        if ($config['far_zone'] <= $config['close_zone']) {
            throw new \InvalidArgumentException('far_zone должна быть больше close_zone');
        }

        // Проверка диапазонов для pH
        if ($type === 'ph') {
            if ($config['target'] < 4 || $config['target'] > 9) {
                throw new \InvalidArgumentException('target для pH должен быть в диапазоне 4-9');
            }
        }

        // Проверка диапазонов для EC
        if ($type === 'ec') {
            if ($config['target'] < 0 || $config['target'] > 10) {
                throw new \InvalidArgumentException('target для EC должен быть в диапазоне 0-10');
            }
        }

        if (! isset($config['max_integral']) || ! is_numeric($config['max_integral']) || (float) $config['max_integral'] <= 0) {
            throw new \InvalidArgumentException('max_integral должен быть положительным числом');
        }
    }

    /**
     * Получить все конфиги для зоны
     */
    public function getAllConfigs(int $zoneId): array
    {
        $configs = ZonePidConfig::where('zone_id', $zoneId)->get();
        $result = [];

        foreach ($configs as $config) {
            $result[$config->type] = $config;
        }

        return $result;
    }

    private function defaultNamespace(string $type): string
    {
        return $type === 'ph' ? 'pid_defaults_ph' : 'pid_defaults_ec';
    }

    /**
     * @return array<string, mixed>
     */
    private function catalogDefaultConfig(string $type): array
    {
        return SystemAutomationSettingsCatalog::defaults($this->defaultNamespace($type));
    }

    private function isValidDefaultConfig(mixed $config): bool
    {
        if (! is_array($config) || array_is_list($config)) {
            return false;
        }

        foreach ([
            'target',
            'dead_zone',
            'close_zone',
            'far_zone',
            'max_output',
            'min_interval_ms',
            'max_integral',
        ] as $key) {
            if (! array_key_exists($key, $config)) {
                return false;
            }
        }

        foreach (['close', 'far'] as $zone) {
            $coeffs = $config['zone_coeffs'][$zone] ?? null;
            if (! is_array($coeffs) || array_is_list($coeffs)) {
                return false;
            }
            foreach (['kp', 'ki', 'kd'] as $key) {
                if (! array_key_exists($key, $coeffs)) {
                    return false;
                }
            }
        }

        return true;
    }
}
