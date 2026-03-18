<?php

namespace App\Support\Recipes;

use App\Models\RecipeRevisionPhase;

class RecipePhasePayloadNormalizer
{
    /**
     * @param  array<string, mixed>  $data
     * @return array<string, mixed>
     */
    public function normalizeForWrite(array $data): array
    {
        if (array_key_exists('stage_template_id', $data) && ($data['stage_template_id'] === '' || $data['stage_template_id'] === 0)) {
            $data['stage_template_id'] = null;
        }

        if (! array_key_exists('duration_hours', $data) && array_key_exists('duration_days', $data) && is_numeric($data['duration_days'])) {
            $data['duration_hours'] = (int) round(((float) $data['duration_days']) * 24);
        }

        if (! array_key_exists('ph_target', $data) && array_key_exists('ph_min', $data) && array_key_exists('ph_max', $data)
            && is_numeric($data['ph_min']) && is_numeric($data['ph_max'])) {
            $data['ph_target'] = round((((float) $data['ph_min']) + ((float) $data['ph_max'])) / 2, 2);
        }

        if (! array_key_exists('ec_target', $data) && array_key_exists('ec_min', $data) && array_key_exists('ec_max', $data)
            && is_numeric($data['ec_min']) && is_numeric($data['ec_max'])) {
            $data['ec_target'] = round((((float) $data['ec_min']) + ((float) $data['ec_max'])) / 2, 2);
        }

        if (array_key_exists('extensions', $data) && is_array($data['extensions'])) {
            $data['extensions'] = $this->normalizeExtensions($data['extensions']);
        }

        return $data;
    }

    /**
     * @param  array<string, mixed>|null  $extensions
     * @return array<string, mixed>|null
     */
    public function normalizeExtensions(?array $extensions): ?array
    {
        if ($extensions === null) {
            return null;
        }

        $normalized = $extensions;

        $dayTarget = is_array($normalized['day_target'] ?? null) ? $normalized['day_target'] : [];
        $nightTarget = is_array($normalized['night_target'] ?? null) ? $normalized['night_target'] : [];
        $dayNight = is_array($normalized['day_night'] ?? null) ? $normalized['day_night'] : [];

        if (! empty($dayTarget) || ! empty($nightTarget)) {
            $temperature = is_array($dayNight['temperature'] ?? null) ? $dayNight['temperature'] : [];
            $humidity = is_array($dayNight['humidity'] ?? null) ? $dayNight['humidity'] : [];

            if (array_key_exists('temp_air', $dayTarget) && ! array_key_exists('day', $temperature)) {
                $temperature['day'] = $dayTarget['temp_air'];
            }
            if (array_key_exists('temp_air', $nightTarget) && ! array_key_exists('night', $temperature)) {
                $temperature['night'] = $nightTarget['temp_air'];
            }
            if (array_key_exists('humidity', $dayTarget) && ! array_key_exists('day', $humidity)) {
                $humidity['day'] = $dayTarget['humidity'];
            }
            if (array_key_exists('humidity', $nightTarget) && ! array_key_exists('night', $humidity)) {
                $humidity['night'] = $nightTarget['humidity'];
            }

            if (! empty($temperature)) {
                $dayNight['temperature'] = $temperature;
            }
            if (! empty($humidity)) {
                $dayNight['humidity'] = $humidity;
            }
            if (! empty($dayNight)) {
                $normalized['day_night'] = $dayNight;
            }
        }

        unset($normalized['day_target'], $normalized['night_target']);

        return empty($normalized) ? null : $normalized;
    }

    /**
     * @param  array<string, mixed>|RecipeRevisionPhase  $phase
     * @return array<string, mixed>
     */
    public function normalizeForRead(array|RecipeRevisionPhase $phase): array
    {
        $data = $phase instanceof RecipeRevisionPhase ? $phase->toArray() : $phase;
        $extensions = is_array($data['extensions'] ?? null) ? $data['extensions'] : null;
        $data['extensions'] = $this->normalizeExtensions($extensions);

        return $data;
    }
}
