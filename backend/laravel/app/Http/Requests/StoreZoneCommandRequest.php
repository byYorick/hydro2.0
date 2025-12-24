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
            
            // Ensure params is an associative array (object), not a list
            if (isset($data['params']) && is_array($data['params']) && array_is_list($data['params'])) {
                $validator->errors()->add('params', 'The params field must be an object, not a list.');
            }

            // Специальная валидация для GROWTH_CYCLE_CONFIG
            if (($data['type'] ?? '') === 'GROWTH_CYCLE_CONFIG') {
                $params = $data['params'] ?? [];

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
        });
    }
}

