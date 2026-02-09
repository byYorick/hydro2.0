<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class SetupWizardValidateDevicesRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        return [
            'zone_id' => ['required', 'integer', 'exists:zones,id'],
            'assignments' => ['required', 'array'],
            'assignments.irrigation' => ['required', 'integer', 'exists:nodes,id'],
            'assignments.correction' => ['required', 'integer', 'exists:nodes,id'],
            'assignments.accumulation' => ['required', 'integer', 'exists:nodes,id'],
            'assignments.climate' => ['nullable', 'integer', 'exists:nodes,id'],
            'assignments.light' => ['nullable', 'integer', 'exists:nodes,id'],
            'selected_node_ids' => ['nullable', 'array'],
            'selected_node_ids.*' => ['integer', 'exists:nodes,id'],
        ];
    }

    public function messages(): array
    {
        return [
            'assignments.irrigation.required' => 'Нужно выбрать узел полива.',
            'assignments.correction.required' => 'Нужно выбрать узел коррекции.',
            'assignments.accumulation.required' => 'Нужно выбрать накопительный узел.',
        ];
    }
}
