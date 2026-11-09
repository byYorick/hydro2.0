<?php

namespace App\Http\Requests;

use App\Models\Plant;
use Illuminate\Foundation\Http\FormRequest;

class StorePlantPriceRequest extends FormRequest
{
    public function authorize(): bool
    {
        $plant = $this->route('plant');

        return $plant instanceof Plant
            && ($this->user()?->can('update', $plant) ?? false);
    }

    public function rules(): array
    {
        return [
            'effective_from' => ['nullable', 'date'],
            'effective_to' => ['nullable', 'date', 'after_or_equal:effective_from'],
            'currency' => ['nullable', 'string', 'max:8'],
            'seedling_cost' => ['nullable', 'numeric', 'min:0'],
            'substrate_cost' => ['nullable', 'numeric', 'min:0'],
            'nutrient_cost' => ['nullable', 'numeric', 'min:0'],
            'labor_cost' => ['nullable', 'numeric', 'min:0'],
            'protection_cost' => ['nullable', 'numeric', 'min:0'],
            'logistics_cost' => ['nullable', 'numeric', 'min:0'],
            'other_cost' => ['nullable', 'numeric', 'min:0'],
            'wholesale_price' => ['nullable', 'numeric', 'min:0'],
            'retail_price' => ['nullable', 'numeric', 'min:0'],
            'source' => ['nullable', 'string', 'max:255'],
        ];
    }
}
