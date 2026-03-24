<?php

namespace App\Services;

use App\Models\AutomationConfigPreset;
use App\Models\AutomationConfigPresetVersion;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

class AutomationConfigPresetService
{
    public function __construct(
        private readonly AutomationConfigRegistry $registry,
    ) {
    }

    public function list(string $namespace): array
    {
        return AutomationConfigPreset::query()
            ->where('namespace', $namespace)
            ->orderByRaw("CASE WHEN scope = 'system' THEN 0 ELSE 1 END")
            ->orderBy('name')
            ->get()
            ->map(fn (AutomationConfigPreset $preset) => $this->serialize($preset))
            ->all();
    }

    public function create(string $namespace, array $payload, ?int $userId = null): AutomationConfigPreset
    {
        $this->assertPresetNamespace($namespace);
        $presetPayload = is_array($payload['payload'] ?? null) ? $payload['payload'] : [];
        $this->registry->validate($namespace, $presetPayload);

        return DB::transaction(function () use ($namespace, $payload, $presetPayload, $userId): AutomationConfigPreset {
            $preset = AutomationConfigPreset::query()->create([
                'namespace' => $namespace,
                'scope' => 'custom',
                'is_locked' => false,
                'name' => (string) ($payload['name'] ?? 'Preset'),
                'slug' => $this->uniqueSlug((string) ($payload['name'] ?? 'Preset')),
                'description' => $payload['description'] ?? null,
                'schema_version' => $this->registry->schemaVersion($namespace),
                'payload' => $presetPayload,
                'updated_by' => $userId,
            ]);

            $this->recordVersion($preset, $userId);

            return $preset->fresh();
        });
    }

    public function update(AutomationConfigPreset $preset, array $payload, ?int $userId = null): AutomationConfigPreset
    {
        if ($preset->is_locked || $preset->scope === 'system') {
            throw new \DomainException('System presets are read-only.');
        }

        $presetPayload = array_key_exists('payload', $payload)
            ? (is_array($payload['payload']) ? $payload['payload'] : [])
            : (is_array($preset->payload) ? $preset->payload : []);
        $this->registry->validate((string) $preset->namespace, $presetPayload);

        return DB::transaction(function () use ($preset, $payload, $presetPayload, $userId): AutomationConfigPreset {
            if (! empty($payload['name']) && (string) $payload['name'] !== (string) $preset->name) {
                $preset->name = (string) $payload['name'];
                $preset->slug = $this->uniqueSlug((string) $payload['name'], (int) $preset->id);
            }

            if (array_key_exists('description', $payload)) {
                $preset->description = $payload['description'];
            }

            $preset->payload = $presetPayload;
            $preset->updated_by = $userId;
            $preset->save();

            $this->recordVersion($preset, $userId);

            return $preset->fresh();
        });
    }

    public function delete(AutomationConfigPreset $preset): void
    {
        if ($preset->is_locked || $preset->scope === 'system') {
            throw new \DomainException('System presets cannot be deleted.');
        }

        $preset->delete();
    }

    public function duplicate(AutomationConfigPreset $preset, ?int $userId = null): AutomationConfigPreset
    {
        return $this->create((string) $preset->namespace, [
            'name' => (string) $preset->name.' copy',
            'description' => $preset->description,
            'payload' => is_array($preset->payload) ? $preset->payload : [],
        ], $userId);
    }

    public function findOrFail(int $presetId, ?string $namespace = null): AutomationConfigPreset
    {
        return AutomationConfigPreset::query()
            ->when($namespace !== null, fn ($query) => $query->where('namespace', $namespace))
            ->findOrFail($presetId);
    }

    /**
     * @return array<string, mixed>
     */
    public function serialize(AutomationConfigPreset $preset): array
    {
        return [
            'id' => $preset->id,
            'namespace' => $preset->namespace,
            'scope' => $preset->scope,
            'is_locked' => (bool) $preset->is_locked,
            'name' => $preset->name,
            'slug' => $preset->slug,
            'description' => $preset->description,
            'schema_version' => $preset->schema_version,
            'payload' => is_array($preset->payload) ? $preset->payload : [],
            'updated_by' => $preset->updated_by,
            'updated_at' => optional($preset->updated_at)->toISOString(),
        ];
    }

    private function recordVersion(AutomationConfigPreset $preset, ?int $userId): void
    {
        $payload = is_array($preset->payload) ? $preset->payload : [];
        AutomationConfigPresetVersion::query()->create([
            'preset_id' => $preset->id,
            'namespace' => $preset->namespace,
            'scope' => $preset->scope,
            'schema_version' => $preset->schema_version,
            'payload' => $payload,
            'checksum' => sha1(json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR)),
            'changed_by' => $userId,
            'changed_at' => now(),
        ]);
    }

    private function assertPresetNamespace(string $namespace): void
    {
        if (! $this->registry->isPresetNamespace($namespace)) {
            throw new \InvalidArgumentException("Namespace {$namespace} does not support presets.");
        }
    }

    private function uniqueSlug(string $name, ?int $ignoreId = null): string
    {
        $base = Str::slug($name);
        if ($base === '') {
            $base = 'automation-preset';
        }

        $slug = $base;
        $index = 1;
        while (
            AutomationConfigPreset::query()
                ->when($ignoreId !== null, fn ($query) => $query->where('id', '!=', $ignoreId))
                ->where('slug', $slug)
                ->exists()
        ) {
            $index += 1;
            $slug = "{$base}-{$index}";
        }

        return $slug;
    }
}
