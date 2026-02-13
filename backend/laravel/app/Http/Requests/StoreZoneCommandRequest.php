<?php

namespace App\Http\Requests;

use App\Models\ZoneAutomationLogicProfile;
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
            $rawParams = $data['params'] ?? [];
            $params = is_array($rawParams) ? $rawParams : [];
            
            // Ensure params is an associative array (object), not a list
            if (is_array($rawParams) && array_is_list($rawParams)) {
                $validator->errors()->add('params', 'The params field must be an object, not a list.');
            }

            // Специальная валидация для GROWTH_CYCLE_CONFIG
            if (($data['type'] ?? '') === 'GROWTH_CYCLE_CONFIG') {

                // Проверяем наличие mode
                if (!isset($params['mode']) || !in_array($params['mode'], ['start', 'adjust'], true)) {
                    $validator->errors()->add('params.mode', 'The params.mode field is required and must be "start" or "adjust" for GROWTH_CYCLE_CONFIG.');
                }

                $allowedModes = ZoneAutomationLogicProfile::allowedModes();
                $profileMode = $params['profile_mode'] ?? null;
                if (!is_string($profileMode) || !in_array($profileMode, $allowedModes, true)) {
                    $validator->errors()->add(
                        'params.profile_mode',
                        'The params.profile_mode field is required and must be one of: '.implode(', ', $allowedModes).'.'
                    );
                }

                if (array_key_exists('subsystems', $params)) {
                    $validator->errors()->add(
                        'params.subsystems',
                        'The params.subsystems field is not allowed. Persist configuration via /api/zones/{zone}/automation-logic-profile.'
                    );
                }
            }

            $type = $data['type'] ?? '';

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
