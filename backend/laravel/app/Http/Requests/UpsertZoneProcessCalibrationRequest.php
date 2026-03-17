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
            'ec_gain_per_ml' => ['sometimes', 'numeric', 'min:0.001', 'max:10'],
            'ph_up_gain_per_ml' => ['sometimes', 'numeric', 'min:0.001', 'max:5'],
            'ph_down_gain_per_ml' => ['sometimes', 'numeric', 'min:0.001', 'max:5'],
            'ph_per_ec_ml' => ['nullable', 'numeric', 'min:-2', 'max:2'],
            'ec_per_ph_ml' => ['nullable', 'numeric', 'min:-2', 'max:2'],
            'transport_delay_sec' => ['nullable', 'integer', 'min:0', 'max:120'],
            'settle_sec' => ['nullable', 'integer', 'min:0', 'max:300'],
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
            'ec_gain_per_ml.min' => 'ec_gain_per_ml должен быть >= 0.001.',
            'ec_gain_per_ml.max' => 'ec_gain_per_ml не может превышать 10.',
            'ph_up_gain_per_ml.min' => 'ph_up_gain_per_ml должен быть >= 0.001.',
            'ph_up_gain_per_ml.max' => 'ph_up_gain_per_ml не может превышать 5.',
            'ph_up_gain_per_ml.numeric' => 'ph_up_gain_per_ml должен быть числом и не может быть null.',
            'ph_down_gain_per_ml.min' => 'ph_down_gain_per_ml должен быть >= 0.001.',
            'ph_down_gain_per_ml.max' => 'ph_down_gain_per_ml не может превышать 5.',
            'ph_down_gain_per_ml.numeric' => 'ph_down_gain_per_ml должен быть числом и не может быть null.',
            'ec_gain_per_ml.numeric' => 'ec_gain_per_ml должен быть числом и не может быть null.',
            'ph_per_ec_ml.min' => 'ph_per_ec_ml должен быть в диапазоне -2..2.',
            'ph_per_ec_ml.max' => 'ph_per_ec_ml должен быть в диапазоне -2..2.',
            'ec_per_ph_ml.min' => 'ec_per_ph_ml должен быть в диапазоне -2..2.',
            'ec_per_ph_ml.max' => 'ec_per_ph_ml должен быть в диапазоне -2..2.',
            'confidence.max' => 'Confidence должна быть в диапазоне 0..1.',
            'transport_delay_sec.max' => 'transport_delay_sec не может превышать 120 секунд.',
            'settle_sec.max' => 'settle_sec не может превышать 300 секунд.',
            'meta.observe.window_min_samples.min' => 'window_min_samples должен быть >= 2.',
            'meta.observe.min_effect_fraction.min' => 'min_effect_fraction должен быть >= 0.01.',
        ];
    }
}
