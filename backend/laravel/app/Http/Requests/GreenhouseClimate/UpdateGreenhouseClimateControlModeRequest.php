<?php

namespace App\Http\Requests\GreenhouseClimate;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class UpdateGreenhouseClimateControlModeRequest extends FormRequest
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
            'control_mode' => ['required', Rule::in(['auto', 'semi', 'manual'])],
        ];
    }
}
