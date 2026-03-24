<?php

namespace App\Services;

use App\Models\AutomationConfigPreset;

class ZoneCorrectionPresetService
{
    public function __construct(
        private readonly AutomationConfigPresetService $presets,
    ) {
    }

    public function list(): array
    {
        return array_map(function (array $preset): array {
            $preset['config'] = $preset['payload'] ?? [];
            unset($preset['payload'], $preset['namespace'], $preset['schema_version']);

            return $preset;
        }, $this->presets->list(AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION));
    }

    public function create(array $payload, ?int $userId = null): AutomationConfigPreset
    {
        return $this->presets->create(AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION, [
            'name' => $payload['name'] ?? 'Preset',
            'description' => $payload['description'] ?? null,
            'payload' => is_array($payload['config'] ?? null) ? $payload['config'] : [],
        ], $userId);
    }

    public function update(AutomationConfigPreset $preset, array $payload, ?int $userId = null): AutomationConfigPreset
    {
        return $this->presets->update($preset, [
            'name' => $payload['name'] ?? $preset->name,
            'description' => $payload['description'] ?? $preset->description,
            'payload' => array_key_exists('config', $payload) && is_array($payload['config']) ? $payload['config'] : $preset->payload,
        ], $userId);
    }

    public function updateById(int $presetId, array $payload, ?int $userId = null): AutomationConfigPreset
    {
        return $this->update(
            $this->presets->findOrFail($presetId, AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION),
            $payload,
            $userId
        );
    }

    public function delete(AutomationConfigPreset $preset): void
    {
        $this->presets->delete($preset);
    }

    public function deleteById(int $presetId): void
    {
        $this->delete(
            $this->presets->findOrFail($presetId, AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION)
        );
    }
}
