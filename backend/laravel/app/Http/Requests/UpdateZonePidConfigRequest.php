<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class UpdateZonePidConfigRequest extends FormRequest
{
    /**
     * Determine if the user is authorized to make this request.
     */
    public function authorize(): bool
    {
        return true; // Авторизация через middleware
    }

    /**
     * Get the validation rules that apply to the request.
     */
    public function rules(): array
    {
        $type = $this->route('type');
        $isPh = $type === 'ph';

        return [
            'config' => ['required', 'array'],
            'config.target' => [
                'required',
                'numeric',
                $isPh ? 'min:0' : 'min:0',
                $isPh ? 'max:14' : 'max:10',
            ],
            'config.dead_zone' => ['required', 'numeric', 'min:0', 'max:2'],
            'config.close_zone' => ['required', 'numeric', 'min:0', 'max:5'],
            'config.far_zone' => ['required', 'numeric', 'min:0', 'max:10'],
            'config.zone_coeffs' => ['required', 'array'],
            'config.zone_coeffs.close' => ['required', 'array'],
            'config.zone_coeffs.close.kp' => ['required', 'numeric', 'min:0', 'max:1000'],
            'config.zone_coeffs.close.ki' => ['required', 'numeric', 'min:0', 'max:100'],
            'config.zone_coeffs.close.kd' => ['required', 'numeric', 'min:0', 'max:100'],
            'config.zone_coeffs.far' => ['required', 'array'],
            'config.zone_coeffs.far.kp' => ['required', 'numeric', 'min:0', 'max:1000'],
            'config.zone_coeffs.far.ki' => ['required', 'numeric', 'min:0', 'max:100'],
            'config.zone_coeffs.far.kd' => ['required', 'numeric', 'min:0', 'max:100'],
            'config.max_output' => ['required', 'numeric', 'min:0', 'max:1000'],
            'config.min_interval_ms' => ['required', 'integer', 'min:1000', 'max:3600000'],
            'config.enable_autotune' => ['required', 'boolean'],
            'config.adaptation_rate' => ['required', 'numeric', 'min:0', 'max:1'],
        ];
    }

    /**
     * Configure the validator instance.
     */
    public function withValidator($validator)
    {
        $validator->after(function ($validator) {
            $config = $this->input('config');

            if (isset($config['dead_zone']) && isset($config['close_zone']) && isset($config['far_zone'])) {
                if ($config['close_zone'] <= $config['dead_zone']) {
                    $validator->errors()->add('config.close_zone', 'Ближняя зона должна быть больше мертвой зоны.');
                }

                if ($config['far_zone'] <= $config['close_zone']) {
                    $validator->errors()->add('config.far_zone', 'Дальняя зона должна быть больше ближней зоны.');
                }
            }
        });
    }

    /**
     * Get custom messages for validator errors.
     */
    public function messages(): array
    {
        return [
            'config.target.required' => 'Целевое значение обязательно для заполнения.',
            'config.target.numeric' => 'Целевое значение должно быть числом.',
            'config.dead_zone.required' => 'Мертвая зона обязательна для заполнения.',
            'config.close_zone.required' => 'Ближняя зона обязательна для заполнения.',
            'config.far_zone.required' => 'Дальняя зона обязательна для заполнения.',
            'config.zone_coeffs.close.kp.required' => 'Коэффициент Kp для близкой зоны обязателен.',
            'config.zone_coeffs.far.kp.required' => 'Коэффициент Kp для дальней зоны обязателен.',
            'config.max_output.required' => 'Максимальный выход обязателен для заполнения.',
            'config.min_interval_ms.required' => 'Минимальный интервал обязателен для заполнения.',
            'config.min_interval_ms.min' => 'Минимальный интервал не может быть меньше 1000 мс.',
            'config.enable_autotune.required' => 'Параметр enable_autotune обязателен для заполнения.',
            'config.adaptation_rate.required' => 'Параметр adaptation_rate обязателен для заполнения.',
        ];
    }
}
