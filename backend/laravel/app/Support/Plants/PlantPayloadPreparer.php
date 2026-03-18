<?php

namespace App\Support\Plants;

use App\Models\Plant;
use Illuminate\Support\Arr;
use Illuminate\Support\Str;

class PlantPayloadPreparer
{
    /**
     * @param  array<string, mixed>  $input
     * @return array<string, mixed>
     */
    public function prepare(array $input, ?Plant $plant = null): array
    {
        $payload = $input;
        $payload['slug'] = $input['slug']
            ?? $plant?->slug
            ?? Str::slug(($input['name'] ?? 'plant').'-'.Str::random(4));

        $payload['environment_requirements'] = $this->sanitizeEnvironment(
            Arr::get($input, 'environment_requirements')
        );

        if (empty($payload['environment_requirements'])) {
            $payload['environment_requirements'] = null;
        }

        if (empty($payload['growth_phases'])) {
            $payload['growth_phases'] = null;
        }

        if (empty($payload['recommended_recipes'])) {
            $payload['recommended_recipes'] = null;
        }

        if (empty($payload['metadata'])) {
            $payload['metadata'] = null;
        }

        return $payload;
    }

    /**
     * @return array<string, array{min: float|null, max: float|null}>|null
     */
    private function sanitizeEnvironment(mixed $value): ?array
    {
        if (! is_array($value)) {
            return null;
        }

        $normalized = [];
        foreach ($value as $metric => $range) {
            if (! is_array($range)) {
                continue;
            }

            $min = $this->nullableFloat($range['min'] ?? null);
            $max = $this->nullableFloat($range['max'] ?? null);

            if ($min === null && $max === null) {
                continue;
            }

            $normalized[$metric] = [
                'min' => $min,
                'max' => $max,
            ];
        }

        return empty($normalized) ? null : $normalized;
    }

    private function nullableFloat(mixed $value): ?float
    {
        if ($value === null || $value === '') {
            return null;
        }

        return is_numeric($value) ? (float) $value : null;
    }
}
