<?php

namespace App\Services;

use App\Models\ZoneEvent;
use App\Support\Automation\ZonePidConfiguration;
use Illuminate\Support\Facades\Log;

class ZonePidConfigurationService
{
    public function __construct(
        private readonly AutomationConfigDocumentService $documents,
        private readonly AutomationConfigRegistry $registry,
    ) {
    }

    /**
     * @return array<string, mixed>
     */
    public function serializeConfig(ZonePidConfiguration $config): array
    {
        return [
            'id' => $config->id,
            'zone_id' => $config->zoneId,
            'type' => $config->type,
            'config' => $config->config,
            'updated_by' => $config->updatedBy,
            'updated_at' => optional($config->updatedAt)->toISOString(),
            'is_default' => false,
        ];
    }

    /**
     * Получить конфиг PID для зоны и типа
     */
    public function getConfig(int $zoneId, string $type): ?ZonePidConfiguration
    {
        $document = $this->documents->getDocument(
            $this->registry->pidNamespace($type),
            AutomationConfigRegistry::SCOPE_ZONE,
            $zoneId,
            false
        );
        $payload = is_array($document?->payload) ? $document->payload : [];
        if ($payload === []) {
            return null;
        }

        return $this->makeTransientConfig(
            $zoneId,
            $type,
            $this->normalizePidConfig($type, $payload),
            $document?->updated_by,
            $document?->updated_at,
            $document?->id
        );
    }

    /**
     * Создать или обновить конфиг PID
     */
    public function createOrUpdate(int $zoneId, string $type, array $config, ?int $userId = null): ZonePidConfiguration
    {
        $config = $this->normalizePidConfig($type, $config);
        $existing = $this->getConfig($zoneId, $type);
        $oldConfig = $existing?->config;
        $document = $this->documents->upsertDocument(
            $this->registry->pidNamespace($type),
            AutomationConfigRegistry::SCOPE_ZONE,
            $zoneId,
            $config,
            $userId,
            'zone_pid_config'
        );

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

        return $this->makeTransientConfig(
            $zoneId,
            $type,
            $this->normalizePidConfig($type, is_array($document->payload) ? $document->payload : []),
            $document->updated_by,
            $document->updated_at,
            $document->id
        );
    }

    /**
     * Получить дефолтный конфиг для типа
     * Значения берутся из authority system documents с fallback на встроенные каталожные defaults.
     */
    public function getDefaultConfig(string $type): array
    {
        $namespace = $this->defaultNamespace($type);

        $config = $this->documents->getSystemPayloadByLegacyNamespace($namespace, true);
        $config = $this->normalizePidConfig($type, $config);

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
     * @param  array<string, mixed>  $config
     * @return array<string, mixed>
     */
    public function sanitizeConfig(array $config, string $type): array
    {
        return array_is_list($config) ? [] : $config;
    }

    /**
     * Получить все конфиги для зоны
     */
    public function getAllConfigs(int $zoneId): array
    {
        $result = [];

        foreach (['ph', 'ec'] as $type) {
            $config = $this->getConfig($zoneId, $type);
            if ($config instanceof ZonePidConfiguration) {
                $result[$type] = $config;
            }
        }

        return $result;
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function makeTransientConfig(
        int $zoneId,
        string $type,
        array $payload,
        ?int $updatedBy = null,
        mixed $updatedAt = null,
        ?int $documentId = null,
    ): ZonePidConfiguration
    {
        return new ZonePidConfiguration(
            id: $documentId,
            zoneId: $zoneId,
            type: $type,
            config: $payload,
            updatedBy: $updatedBy,
            updatedAt: $updatedAt,
        );
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
        return $this->normalizePidConfig($type, SystemAutomationSettingsCatalog::defaults($this->defaultNamespace($type)));
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

    /**
     * @param  array<string, mixed>  $config
     * @return array<string, mixed>
     */
    private function normalizePidConfig(string $type, array $config): array
    {
        if (array_is_list($config)) {
            return [];
        }

        return $this->normalizeAgainstTemplate(
            $config,
            SystemAutomationSettingsCatalog::defaults($this->defaultNamespace($type))
        );
    }

    /**
     * @param  array<string, mixed>  $config
     * @param  array<string, mixed>  $template
     * @return array<string, mixed>
     */
    private function normalizeAgainstTemplate(array $config, array $template): array
    {
        $normalized = [];

        foreach ($config as $key => $value) {
            $templateValue = $template[$key] ?? null;

            if (is_array($value) && ! array_is_list($value) && is_array($templateValue) && ! array_is_list($templateValue)) {
                $normalized[$key] = $this->normalizeAgainstTemplate($value, $templateValue);
                continue;
            }

            if (is_float($templateValue) && is_numeric($value)) {
                $normalized[$key] = (float) $value;
                continue;
            }

            if (is_int($templateValue) && is_numeric($value)) {
                $normalized[$key] = (int) $value;
                continue;
            }

            $normalized[$key] = $value;
        }

        return $normalized;
    }
}
