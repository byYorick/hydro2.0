<?php

namespace App\Http\Requests\GreenhouseClimate;

use Illuminate\Foundation\Http\FormRequest;

class DeleteGreenhouseClimateManualOverrideRequest extends FormRequest
{
    public function authorize(): bool
    {
        return $this->user() !== null;
    }

    /**
     * @return array<string, array<int, string>>
     */
    public function rules(): array
    {
        return [];
    }
}
