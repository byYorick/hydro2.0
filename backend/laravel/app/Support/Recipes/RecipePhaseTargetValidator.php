<?php

namespace App\Support\Recipes;

use App\Models\RecipeRevisionPhase;
use Illuminate\Support\Facades\Validator;

class RecipePhaseTargetValidator
{
    /**
     * @param  array<string, mixed>  $data
     */
    public function validateForStore(array $data, string $attributePrefix = ''): void
    {
        $validator = Validator::make($data, []);
        $validator->after(function (\Illuminate\Validation\Validator $v) use ($data, $attributePrefix): void {
            $this->applyValidation($v, $data, null, false, $attributePrefix);
        });
        $validator->validate();
    }

    /**
     * @param  array<string, mixed>  $data
     */
    public function validateForUpdate(array $data, RecipeRevisionPhase $existingPhase, string $attributePrefix = ''): void
    {
        $validator = Validator::make($data, []);
        $validator->after(function (\Illuminate\Validation\Validator $v) use ($data, $existingPhase, $attributePrefix): void {
            $this->applyValidation($v, $data, $existingPhase, true, $attributePrefix);
        });
        $validator->validate();
    }

    /**
     * @param  array<string, mixed>  $data
     */
    public function appendStoreErrors(mixed $validator, array $data, string $attributePrefix = ''): void
    {
        $this->applyValidation($validator, $data, null, false, $attributePrefix);
    }

    /**
     * @param  array<string, mixed>  $data
     */
    public function appendUpdateErrors(
        mixed $validator,
        array $data,
        RecipeRevisionPhase $existingPhase,
        string $attributePrefix = ''
    ): void {
        $this->applyValidation($validator, $data, $existingPhase, true, $attributePrefix);
    }

    /**
     * @param  array<string, mixed>  $data
     */
    private function applyValidation(
        mixed $validator,
        array $data,
        ?RecipeRevisionPhase $existingPhase,
        bool $partial,
        string $attributePrefix
    ): void {
        $this->validateMetric(
            validator: $validator,
            data: $data,
            existingPhase: $existingPhase,
            partial: $partial,
            metric: 'ph',
            targetField: 'ph_target',
            minField: 'ph_min',
            maxField: 'ph_max',
            label: 'pH',
            attributePrefix: $attributePrefix,
        );

        $this->validateMetric(
            validator: $validator,
            data: $data,
            existingPhase: $existingPhase,
            partial: $partial,
            metric: 'ec',
            targetField: 'ec_target',
            minField: 'ec_min',
            maxField: 'ec_max',
            label: 'EC',
            attributePrefix: $attributePrefix,
        );

        $this->validateDayNightExtensions($validator, $data, $attributePrefix);
    }

    /**
     * @param  array<string, mixed>  $data
     */
    private function validateDayNightExtensions($validator, array $data, string $attributePrefix): void
    {
        if (! array_key_exists('day_night_enabled', $data) && ! array_key_exists('extensions', $data)) {
            return;
        }

        $enabled = (bool) ($data['day_night_enabled'] ?? false);
        $extensions = is_array($data['extensions'] ?? null) ? $data['extensions'] : null;
        $dayNight = is_array($extensions['day_night'] ?? null) ? $extensions['day_night'] : null;

        if (! $enabled || $dayNight === null) {
            return;
        }

        foreach (['ph' => ['label' => 'pH', 'upper' => 14.0], 'ec' => ['label' => 'EC', 'upper' => 20.0]] as $metric => $spec) {
            $section = is_array($dayNight[$metric] ?? null) ? $dayNight[$metric] : null;
            if ($section === null) {
                continue;
            }

            foreach (['day', 'night'] as $profile) {
                $target = $this->toFloatOrNull($section[$profile] ?? null);
                $min = $this->toFloatOrNull($section[$profile.'_min'] ?? null);
                $max = $this->toFloatOrNull($section[$profile.'_max'] ?? null);

                $attrBase = $attributePrefix.'extensions.day_night.'.$metric.'.'.$profile;
                $label = $spec['label'].' ('.$profile.')';

                if ($min !== null && $max !== null && $min > $max) {
                    $validator->errors()->add($attrBase.'_min', "{$label}: min не может быть больше max.");
                    continue;
                }
                if ($target !== null && $min !== null && $max !== null && ($target < $min || $target > $max)) {
                    $validator->errors()->add($attrBase, "{$label}: target должен быть в диапазоне min..max.");
                }
                foreach (['target' => $target, 'min' => $min, 'max' => $max] as $kind => $value) {
                    if ($value === null) {
                        continue;
                    }
                    if ($value < 0.0 || $value > $spec['upper']) {
                        $attrKey = $kind === 'target' ? $attrBase : $attrBase.'_'.$kind;
                        $validator->errors()->add($attrKey, "{$label}: значение {$kind} вне допустимого диапазона 0..{$spec['upper']}.");
                    }
                }
            }
        }
    }

    private function toFloatOrNull(mixed $value): ?float
    {
        if ($value === null || $value === '') {
            return null;
        }
        return is_numeric($value) ? (float) $value : null;
    }

    /**
     * @param  array<string, mixed>  $data
     */
    private function validateMetric(
        $validator,
        array $data,
        ?RecipeRevisionPhase $existingPhase,
        bool $partial,
        string $metric,
        string $targetField,
        string $minField,
        string $maxField,
        string $label,
        string $attributePrefix = '',
    ): void {
        $hasIncoming = array_key_exists($targetField, $data)
            || array_key_exists($minField, $data)
            || array_key_exists($maxField, $data);

        if ($partial && ! $hasIncoming) {
            return;
        }

        $target = $this->resolveNumeric($data[$targetField] ?? null, $existingPhase?->{$targetField});
        $min = $this->resolveNumeric($data[$minField] ?? null, $existingPhase?->{$minField});
        $max = $this->resolveNumeric($data[$maxField] ?? null, $existingPhase?->{$maxField});
        $targetAttribute = $attributePrefix.$targetField;
        $minAttribute = $attributePrefix.$minField;
        $maxAttribute = $attributePrefix.$maxField;

        if ($target === null) {
            $validator->errors()->add($targetAttribute, "Для {$label} требуется явный target.");
        }
        if ($min === null) {
            $validator->errors()->add($minAttribute, "Для {$label} требуется min.");
        }
        if ($max === null) {
            $validator->errors()->add($maxAttribute, "Для {$label} требуется max.");
        }

        if ($target === null || $min === null || $max === null) {
            return;
        }

        if ($min > $max) {
            $validator->errors()->add($minAttribute, "{$label}: min не может быть больше max.");

            return;
        }

        if ($target < $min || $target > $max) {
            $validator->errors()->add($targetAttribute, "{$label}: target должен быть в диапазоне min..max.");
        }

        if ($metric === 'ph' && ($target < 0.0 || $target > 14.0 || $min < 0.0 || $max > 14.0)) {
            $validator->errors()->add($targetAttribute, 'pH target/min/max должны быть в диапазоне 0..14.');
        }
    }

    private function resolveNumeric(mixed $incoming, mixed $fallback): ?float
    {
        if ($incoming === null || $incoming === '') {
            if ($fallback === null || $fallback === '') {
                return null;
            }

            return is_numeric($fallback) ? (float) $fallback : null;
        }

        return is_numeric($incoming) ? (float) $incoming : null;
    }
}
