<?php

namespace App\Http\Requests;

use App\Support\Recipes\RecipePhasePayloadNormalizer;
use App\Support\Recipes\RecipePhaseRules;
use App\Support\Recipes\RecipePhaseTargetValidator;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Validator;

class StorePlantWithRecipeRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    /**
     * @return array<string, mixed>
     */
    public function rules(): array
    {
        return array_merge([
            'plant' => ['required', 'array'],
            'plant.name' => ['required', 'string', 'max:255'],
            'plant.slug' => ['nullable', 'string', 'max:255', 'unique:plants,slug'],
            'plant.species' => ['nullable', 'string', 'max:255'],
            'plant.variety' => ['nullable', 'string', 'max:255'],
            'plant.substrate_type' => ['nullable', 'string', 'max:100'],
            'plant.growing_system' => ['nullable', 'string', 'max:100'],
            'plant.photoperiod_preset' => ['nullable', 'string', 'max:50'],
            'plant.seasonality' => ['nullable', 'string', 'max:100'],
            'plant.icon_path' => ['nullable', 'string', 'max:255'],
            'plant.description' => ['nullable', 'string'],
            'plant.environment_requirements' => ['nullable', 'array'],
            'plant.environment_requirements.*.min' => ['nullable', 'numeric'],
            'plant.environment_requirements.*.max' => ['nullable', 'numeric'],
            'plant.growth_phases' => ['nullable', 'array'],
            'plant.growth_phases.*.name' => ['required_with:plant.growth_phases', 'string', 'max:255'],
            'plant.growth_phases.*.duration_days' => ['nullable', 'integer', 'min:0'],
            'plant.recommended_recipes' => ['nullable', 'array'],
            'plant.recommended_recipes.*' => ['string', 'max:255'],
            'plant.metadata' => ['nullable', 'array'],
            'recipe' => ['required', 'array'],
            'recipe.name' => ['required', 'string', 'max:255'],
            'recipe.description' => ['nullable', 'string'],
            'recipe.revision_description' => ['nullable', 'string'],
            'recipe.phases' => ['required', 'array', 'min:1'],
        ], RecipePhaseRules::store('recipe.phases.*.'));
    }

    /**
     * @return array<int, \Closure(\Illuminate\Validation\Validator): void>
     */
    public function after(): array
    {
        return [
            function (Validator $validator): void {
                $phaseValidator = app(RecipePhaseTargetValidator::class);
                $normalizer = app(RecipePhasePayloadNormalizer::class);
                $phases = $this->input('recipe.phases', []);

                if (! is_array($phases)) {
                    return;
                }

                foreach ($phases as $index => $phaseData) {
                    if (! is_array($phaseData)) {
                        continue;
                    }

                    $normalized = $normalizer->normalizeForWrite($phaseData);
                    $phaseValidator->appendStoreErrors($validator, $normalized, "recipe.phases.{$index}.");
                }
            },
        ];
    }
}
