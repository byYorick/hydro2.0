<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class UpsertZoneProcessCalibrationRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        return [
            'ec_gain_per_ml' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'ph_up_gain_per_ml' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'ph_down_gain_per_ml' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'ph_per_ec_ml' => ['nullable', 'numeric', 'min:-100', 'max:100'],
            'ec_per_ph_ml' => ['nullable', 'numeric', 'min:-100', 'max:100'],
            'transport_delay_sec' => ['nullable', 'integer', 'min:0', 'max:3600'],
            'settle_sec' => ['nullable', 'integer', 'min:0', 'max:3600'],
            'confidence' => ['nullable', 'numeric', 'min:0', 'max:1'],
            'source' => ['nullable', 'string', 'max:64'],
            'meta' => ['nullable', 'array'],
        ];
    }

    public function messages(): array
    {
        return [
            'confidence.max' => 'Confidence должна быть в диапазоне 0..1.',
            'transport_delay_sec.max' => 'transport_delay_sec не может превышать 3600 секунд.',
            'settle_sec.max' => 'settle_sec не может превышать 3600 секунд.',
        ];
    }
}
