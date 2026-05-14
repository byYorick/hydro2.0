<?php

namespace App\Http\Requests\GreenhouseClimate;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class StoreGreenhouseClimateManualOverrideRequest extends FormRequest
{
    public function authorize(): bool
    {
        return $this->user() !== null;
    }

    /**
     * @return array<string, array<int, mixed>>
     */
    public function rules(): array
    {
        return [
            'left_position_pct' => ['required', 'integer', 'min:0', 'max:100'],
            'right_position_pct' => ['required', 'integer', 'min:0', 'max:100'],
            'ttl_sec' => ['required', 'integer', 'min:60', 'max:86400'],
            'return_mode' => ['required', Rule::in(['auto', 'semi', 'manual'])],
            'reason' => ['nullable', 'string', 'max:500'],
        ];
    }
}
