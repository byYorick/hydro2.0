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
            'meta.observe' => ['nullable', 'array'],
            'meta.observe.telemetry_period_sec' => ['nullable', 'integer', 'min:1', 'max:300'],
            'meta.observe.window_min_samples' => ['nullable', 'integer', 'min:2', 'max:64'],
            'meta.observe.decision_window_sec' => ['nullable', 'integer', 'min:1', 'max:3600'],
            'meta.observe.observe_poll_sec' => ['nullable', 'integer', 'min:1', 'max:300'],
            'meta.observe.min_effect_fraction' => ['nullable', 'numeric', 'min:0.01', 'max:1'],
            'meta.observe.stability_max_slope' => ['nullable', 'numeric', 'min:0.0001', 'max:100'],
            'meta.observe.no_effect_consecutive_limit' => ['nullable', 'integer', 'min:1', 'max:10'],
        ];
    }

    public function messages(): array
    {
        return [
            'confidence.max' => 'Confidence должна быть в диапазоне 0..1.',
            'transport_delay_sec.max' => 'transport_delay_sec не может превышать 3600 секунд.',
            'settle_sec.max' => 'settle_sec не может превышать 3600 секунд.',
            'meta.observe.window_min_samples.min' => 'window_min_samples должен быть >= 2.',
            'meta.observe.min_effect_fraction.min' => 'min_effect_fraction должен быть >= 0.01.',
        ];
    }
}
