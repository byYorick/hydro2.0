<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class StoreZoneCommandRequest extends FormRequest
{
    /**
     * Determine if the user is authorized to make this request.
     */
    public function authorize(): bool
    {
        return true; // Авторизация проверяется в контроллере через Policy
    }

    /**
     * Get the validation rules that apply to the request.
     */
    public function rules(): array
    {
        return [
            'type' => ['required', 'string', 'max:64'],
            'params' => ['nullable', 'array'],
            'node_uid' => ['nullable', 'string', 'max:64'],
            'channel' => ['nullable', 'string', 'max:64'],
        ];
    }

    /**
     * Configure the validator instance.
     */
    public function withValidator($validator): void
    {
        $validator->after(function ($validator) {
            $data = $this->all();
            $params = $data['params'] ?? [];
            
            // Ensure params is an associative array (object), not a list
            if (isset($data['params']) && is_array($data['params']) && array_is_list($data['params'])) {
                $validator->errors()->add('params', 'The params field must be an object, not a list.');
            }

            // Специальная валидация для GROWTH_CYCLE_CONFIG
            if (($data['type'] ?? '') === 'GROWTH_CYCLE_CONFIG') {

                // Проверяем наличие mode
                if (!isset($params['mode']) || !in_array($params['mode'], ['start', 'adjust'], true)) {
                    $validator->errors()->add('params.mode', 'The params.mode field is required and must be "start" or "adjust" for GROWTH_CYCLE_CONFIG.');
                }

                // Проверяем наличие subsystems
                if (!isset($params['subsystems']) || !is_array($params['subsystems'])) {
                    $validator->errors()->add('params.subsystems', 'The params.subsystems field is required and must be an object for GROWTH_CYCLE_CONFIG.');
                } else {
                    // Проверяем обязательные подсистемы
                    $subsystems = $params['subsystems'];
                    $requiredSubsystems = ['ph', 'ec', 'irrigation'];
                    foreach ($requiredSubsystems as $subsystem) {
                        if (!isset($subsystems[$subsystem]) || !is_array($subsystems[$subsystem])) {
                            $validator->errors()->add("params.subsystems.{$subsystem}", "The params.subsystems.{$subsystem} field is required for GROWTH_CYCLE_CONFIG.");
                        } elseif (!isset($subsystems[$subsystem]['enabled']) || $subsystems[$subsystem]['enabled'] !== true) {
                            $validator->errors()->add("params.subsystems.{$subsystem}.enabled", "The params.subsystems.{$subsystem}.enabled must be true (required subsystem).");
                        } elseif ($subsystems[$subsystem]['enabled'] && !isset($subsystems[$subsystem]['targets'])) {
                            $validator->errors()->add("params.subsystems.{$subsystem}.targets", "The params.subsystems.{$subsystem}.targets field is required when enabled.");
                        }
                    }
                }
            }

            $type = $data['type'] ?? '';
            if (!is_array($params)) {
                $params = [];
            }

            if ($type === 'FORCE_IRRIGATION') {
                $duration = $params['duration_sec'] ?? null;
                if (!is_numeric($duration) || $duration < 1 || $duration > 3600) {
                    $validator->errors()->add('params.duration_sec', 'The params.duration_sec must be between 1 and 3600 seconds.');
                }
            }

            if ($type === 'FORCE_PH_CONTROL') {
                $target = $params['target_ph'] ?? null;
                if (!is_numeric($target) || $target < 4.0 || $target > 9.0) {
                    $validator->errors()->add('params.target_ph', 'The params.target_ph must be between 4.0 and 9.0.');
                }
            }

            if ($type === 'FORCE_EC_CONTROL') {
                $target = $params['target_ec'] ?? null;
                if (!is_numeric($target) || $target < 0.1 || $target > 10.0) {
                    $validator->errors()->add('params.target_ec', 'The params.target_ec must be between 0.1 and 10.0.');
                }
            }

            if ($type === 'FORCE_CLIMATE') {
                $temp = $params['target_temp'] ?? null;
                $humidity = $params['target_humidity'] ?? null;
                if (!is_numeric($temp) || $temp < 10 || $temp > 35) {
                    $validator->errors()->add('params.target_temp', 'The params.target_temp must be between 10 and 35.');
                }
                if (!is_numeric($humidity) || $humidity < 30 || $humidity > 90) {
                    $validator->errors()->add('params.target_humidity', 'The params.target_humidity must be between 30 and 90.');
                }
            }

            if ($type === 'FORCE_LIGHTING') {
                $intensity = $params['intensity'] ?? null;
                $duration = $params['duration_hours'] ?? null;
                if (!is_numeric($intensity) || $intensity < 0 || $intensity > 100) {
                    $validator->errors()->add('params.intensity', 'The params.intensity must be between 0 and 100.');
                }
                if (!is_numeric($duration) || $duration < 0.5 || $duration > 24) {
                    $validator->errors()->add('params.duration_hours', 'The params.duration_hours must be between 0.5 and 24 hours.');
                }
            }
        });
    }
}
