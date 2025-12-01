<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class UpdatePlantRequest extends FormRequest
{
    /**
     * Determine if the user is authorized to make this request.
     */
    public function authorize(): bool
    {
        return true;
    }

    /**
     * Get the validation rules that apply to the request.
     *
     * @return array<string, \Illuminate\Contracts\Validation\ValidationRule|array<mixed>|string>
     */
    public function rules(): array
    {
        $plantId = $this->route('plant')?->id;

        return [
            'name' => ['required', 'string', 'max:255'],
            'slug' => [
                'nullable',
                'string',
                'max:255',
                Rule::unique('plants', 'slug')->ignore($plantId),
            ],
            'species' => ['nullable', 'string', 'max:255'],
            'variety' => ['nullable', 'string', 'max:255'],
            'substrate_type' => ['nullable', 'string', 'max:100'],
            'growing_system' => ['nullable', 'string', 'max:100'],
            'photoperiod_preset' => ['nullable', 'string', 'max:50'],
            'seasonality' => ['nullable', 'string', 'max:100'],
            'icon_path' => ['nullable', 'string', 'max:255'],
            'description' => ['nullable', 'string'],
            'environment_requirements' => ['nullable', 'array'],
            'environment_requirements.*.min' => ['nullable', 'numeric'],
            'environment_requirements.*.max' => ['nullable', 'numeric'],
            'growth_phases' => ['nullable', 'array'],
            'growth_phases.*.name' => ['required_with:growth_phases', 'string', 'max:255'],
            'growth_phases.*.duration_days' => ['nullable', 'integer', 'min:0'],
            'recommended_recipes' => ['nullable', 'array'],
            'recommended_recipes.*' => ['string', 'max:255'],
            'metadata' => ['nullable', 'array'],
        ];
    }
}
