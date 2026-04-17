<?php

namespace App\Services;

use App\Models\ZoneAutomationPreset;
use Illuminate\Database\Eloquent\Collection;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

class ZoneAutomationPresetService
{
    /**
     * @param  array{tanks_count?: int, irrigation_system_type?: string}  $filters
     * @return array<int, array<string, mixed>>
     */
    public function list(array $filters = []): array
    {
        return ZoneAutomationPreset::query()
            ->when(
                isset($filters['tanks_count']),
                fn ($q) => $q->where('tanks_count', $filters['tanks_count'])
            )
            ->when(
                isset($filters['irrigation_system_type']),
                fn ($q) => $q->where('irrigation_system_type', $filters['irrigation_system_type'])
            )
            ->orderByRaw("CASE WHEN scope = 'system' THEN 0 ELSE 1 END")
            ->orderBy('name')
            ->get()
            ->map(fn (ZoneAutomationPreset $preset) => $this->serialize($preset))
            ->all();
    }

    /**
     * @param  array<string, mixed>  $data
     */
    public function create(array $data, ?int $userId = null): ZoneAutomationPreset
    {
        return DB::transaction(function () use ($data, $userId): ZoneAutomationPreset {
            return ZoneAutomationPreset::query()->create([
                'name' => (string) $data['name'],
                'slug' => $this->uniqueSlug((string) $data['name']),
                'description' => $data['description'] ?? null,
                'scope' => 'custom',
                'is_locked' => false,
                'tanks_count' => (int) ($data['tanks_count'] ?? 2),
                'irrigation_system_type' => (string) ($data['irrigation_system_type'] ?? 'dwc'),
                'correction_preset_id' => $data['correction_preset_id'] ?? null,
                'correction_profile' => $data['correction_profile'] ?? null,
                'config' => $data['config'] ?? [],
                'created_by' => $userId,
                'updated_by' => $userId,
            ]);
        });
    }

    /**
     * @param  array<string, mixed>  $data
     */
    public function update(ZoneAutomationPreset $preset, array $data, ?int $userId = null): ZoneAutomationPreset
    {
        if ($preset->is_locked || $preset->scope === 'system') {
            throw new \DomainException('System presets are read-only.');
        }

        return DB::transaction(function () use ($preset, $data, $userId): ZoneAutomationPreset {
            if (! empty($data['name']) && (string) $data['name'] !== (string) $preset->name) {
                $preset->name = (string) $data['name'];
                $preset->slug = $this->uniqueSlug((string) $data['name'], (int) $preset->id);
            }

            if (array_key_exists('description', $data)) {
                $preset->description = $data['description'];
            }

            if (array_key_exists('tanks_count', $data)) {
                $preset->tanks_count = (int) $data['tanks_count'];
            }

            if (array_key_exists('irrigation_system_type', $data)) {
                $preset->irrigation_system_type = (string) $data['irrigation_system_type'];
            }

            if (array_key_exists('correction_preset_id', $data)) {
                $preset->correction_preset_id = $data['correction_preset_id'];
            }

            if (array_key_exists('correction_profile', $data)) {
                $preset->correction_profile = $data['correction_profile'];
            }

            if (array_key_exists('config', $data)) {
                $preset->config = $data['config'];
            }

            $preset->updated_by = $userId;
            $preset->save();

            return $preset->fresh();
        });
    }

    public function delete(ZoneAutomationPreset $preset): void
    {
        if ($preset->is_locked || $preset->scope === 'system') {
            throw new \DomainException('System presets cannot be deleted.');
        }

        $preset->delete();
    }

    public function duplicate(ZoneAutomationPreset $preset, ?int $userId = null): ZoneAutomationPreset
    {
        return $this->create([
            'name' => (string) $preset->name.' (копия)',
            'description' => $preset->description,
            'tanks_count' => $preset->tanks_count,
            'irrigation_system_type' => $preset->irrigation_system_type,
            'correction_preset_id' => $preset->correction_preset_id,
            'correction_profile' => $preset->correction_profile,
            'config' => is_array($preset->config) ? $preset->config : [],
        ], $userId);
    }

    public function findOrFail(int $id): ZoneAutomationPreset
    {
        return ZoneAutomationPreset::query()->findOrFail($id);
    }

    /**
     * @return array<string, mixed>
     */
    public function serialize(ZoneAutomationPreset $preset): array
    {
        return [
            'id' => $preset->id,
            'name' => $preset->name,
            'slug' => $preset->slug,
            'description' => $preset->description,
            'scope' => $preset->scope,
            'is_locked' => (bool) $preset->is_locked,
            'tanks_count' => (int) $preset->tanks_count,
            'irrigation_system_type' => $preset->irrigation_system_type,
            'correction_preset_id' => $preset->correction_preset_id,
            'correction_profile' => $preset->correction_profile,
            'config' => is_array($preset->config) ? $preset->config : [],
            'created_by' => $preset->created_by,
            'updated_by' => $preset->updated_by,
            'created_at' => optional($preset->created_at)->toISOString(),
            'updated_at' => optional($preset->updated_at)->toISOString(),
        ];
    }

    private function uniqueSlug(string $name, ?int $ignoreId = null): string
    {
        $base = Str::slug($name);
        if ($base === '') {
            $base = 'zone-automation-preset';
        }

        $slug = $base;
        $index = 1;
        while (
            ZoneAutomationPreset::query()
                ->when($ignoreId !== null, fn ($q) => $q->where('id', '!=', $ignoreId))
                ->where('slug', $slug)
                ->exists()
        ) {
            $index += 1;
            $slug = "{$base}-{$index}";
        }

        return $slug;
    }
}
