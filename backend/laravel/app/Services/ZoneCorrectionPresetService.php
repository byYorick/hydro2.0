<?php

namespace App\Services;

use App\Models\ZoneCorrectionPreset;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

class ZoneCorrectionPresetService
{
    public function list(): array
    {
        return ZoneCorrectionPreset::query()
            ->where('is_active', true)
            ->orderByRaw("CASE WHEN scope = 'system' THEN 0 ELSE 1 END")
            ->orderBy('name')
            ->get()
            ->map(fn (ZoneCorrectionPreset $preset) => [
                'id' => $preset->id,
                'slug' => $preset->slug,
                'name' => $preset->name,
                'scope' => $preset->scope,
                'is_locked' => $preset->is_locked,
                'is_active' => $preset->is_active,
                'description' => $preset->description,
                'config' => $preset->config ?? [],
                'created_by' => $preset->created_by,
                'updated_by' => $preset->updated_by,
                'updated_at' => optional($preset->updated_at)->toISOString(),
            ])
            ->all();
    }

    public function create(array $payload, ?int $userId = null): ZoneCorrectionPreset
    {
        $config = is_array($payload['config'] ?? null) ? $payload['config'] : [];
        $this->validatePresetPayload($config);

        return DB::transaction(function () use ($payload, $config, $userId) {
            return ZoneCorrectionPreset::query()->create([
                'slug' => $this->buildUniqueSlug((string) $payload['name']),
                'name' => (string) $payload['name'],
                'scope' => 'custom',
                'is_locked' => false,
                'is_active' => true,
                'description' => $payload['description'] ?? null,
                'config' => $config,
                'created_by' => $userId,
                'updated_by' => $userId,
            ]);
        });
    }

    public function update(ZoneCorrectionPreset $preset, array $payload, ?int $userId = null): ZoneCorrectionPreset
    {
        if ($preset->is_locked || $preset->scope === 'system') {
            throw new \DomainException('System presets are read-only.');
        }

        $config = array_key_exists('config', $payload)
            ? (is_array($payload['config']) ? $payload['config'] : [])
            : ($preset->config ?? []);
        $this->validatePresetPayload($config);

        return DB::transaction(function () use ($preset, $payload, $config, $userId) {
            if (! empty($payload['name']) && (string) $payload['name'] !== (string) $preset->name) {
                $preset->slug = $this->buildUniqueSlug((string) $payload['name'], $preset->id);
                $preset->name = (string) $payload['name'];
            }

            if (array_key_exists('description', $payload)) {
                $preset->description = $payload['description'];
            }

            $preset->config = $config;
            $preset->updated_by = $userId;
            $preset->save();

            return $preset->fresh();
        });
    }

    public function delete(ZoneCorrectionPreset $preset): void
    {
        if ($preset->is_locked || $preset->scope === 'system') {
            throw new \DomainException('System presets cannot be deleted.');
        }

        DB::transaction(function () use ($preset) {
            if ($preset->zoneConfigs()->exists()) {
                throw new \DomainException('Preset is used by one or more zone correction configs.');
            }
            $preset->delete();
        });
    }

    private function buildUniqueSlug(string $name, ?int $ignoreId = null): string
    {
        $base = Str::slug($name);
        if ($base === '') {
            $base = 'correction-preset';
        }

        $slug = $base;
        $index = 1;
        while (
            ZoneCorrectionPreset::query()
                ->when($ignoreId !== null, fn ($query) => $query->where('id', '!=', $ignoreId))
                ->where('slug', $slug)
                ->exists()
        ) {
            $index += 1;
            $slug = "{$base}-{$index}";
        }

        return $slug;
    }

    private function validatePresetPayload(array $config): void
    {
        if ($config === []) {
            return;
        }

        if (
            isset($config['base'])
            && is_array($config['base'])
            && ! array_is_list($config['base'])
        ) {
            ZoneCorrectionConfigCatalog::validateFragment($config['base'], false);
            $phases = $config['phases'] ?? [];
            if (! is_array($phases) || array_is_list($phases)) {
                throw new \InvalidArgumentException('Preset phases должен быть объектом.');
            }
            foreach ($phases as $phase => $phaseConfig) {
                if (! in_array($phase, ZoneCorrectionConfigCatalog::PHASES, true)) {
                    throw new \InvalidArgumentException("Unsupported preset phase {$phase}.");
                }
                if (! is_array($phaseConfig) || array_is_list($phaseConfig)) {
                    throw new \InvalidArgumentException("Preset phase {$phase} должен быть объектом.");
                }
                ZoneCorrectionConfigCatalog::validateFragment($phaseConfig, false);
            }
            return;
        }

        ZoneCorrectionConfigCatalog::validateFragment($config, false);
    }
}
