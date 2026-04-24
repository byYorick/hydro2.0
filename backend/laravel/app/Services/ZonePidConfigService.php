<?php

namespace App\Services;

use App\Models\ZoneEvent;
use App\Models\ZonePidConfig;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class ZonePidConfigService
{
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
                'details' => [
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
     * Значения соответствуют AutomationSettings из Python-сервиса
     */
    public function getDefaultConfig(string $type): array
    {
        if ($type === 'ph') {
            return [
                'target' => 6.0, // Будет переопределено из рецепта
                'dead_zone' => 0.2,
                'close_zone' => 0.5,
                'far_zone' => 1.0,
                'zone_coeffs' => [
                    'close' => [
                        'kp' => 10.0,
                        'ki' => 0.0,
                        'kd' => 0.0,
                    ],
                    'far' => [
                        'kp' => 12.0,
                        'ki' => 0.0,
                        'kd' => 0.0,
                    ],
                ],
                'max_output' => 50.0,
                'min_interval_ms' => 60000,
                'enable_autotune' => false,
                'adaptation_rate' => 0.05,
            ];
        } else { // ec
            return [
                'target' => 2.0, // Будет переопределено из рецепта
                'dead_zone' => 0.2,
                'close_zone' => 0.5,
                'far_zone' => 1.0,
                'zone_coeffs' => [
                    'close' => [
                        'kp' => 100.0,
                        'ki' => 0.0,
                        'kd' => 0.0,
                    ],
                    'far' => [
                        'kp' => 120.0,
                        'ki' => 0.0,
                        'kd' => 0.0,
                    ],
                ],
                'max_output' => 200.0,
                'min_interval_ms' => 60000,
                'enable_autotune' => false,
                'adaptation_rate' => 0.05,
            ];
        }
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
            if ($config['target'] < 0 || $config['target'] > 14) {
                throw new \InvalidArgumentException('target для pH должен быть в диапазоне 0-14');
            }
        }

        // Проверка диапазонов для EC
        if ($type === 'ec') {
            if ($config['target'] < 0 || $config['target'] > 10) {
                throw new \InvalidArgumentException('target для EC должен быть в диапазоне 0-10');
            }
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
}
