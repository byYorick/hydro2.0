<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class StoreNodeCommandRequest extends FormRequest
{
    /**
     * Determine if the user is authorized to make this request.
     */
    public function authorize(): bool
    {
        return true; // Авторизация проверяется в контроллере
    }

    /**
     * Get the validation rules that apply to the request.
     */
    public function rules(): array
    {
        return [
            'type' => ['nullable', 'string', 'max:64'],
            'cmd' => ['nullable', 'string', 'max:64'],
            'channel' => ['nullable', 'string', 'max:128'],
            'params' => ['nullable', 'array'],
        ];
    }

    /**
     * Configure the validator instance.
     */
    public function withValidator($validator): void
    {
        $validator->after(function ($validator) {
            $data = $this->all();
            
            // Support both 'type' and 'cmd' fields for backward compatibility
            if (!isset($data['cmd']) && isset($data['type'])) {
                $data['cmd'] = $data['type'];
            }
            
            // Ensure cmd is set
            if (!isset($data['cmd'])) {
                $validator->errors()->add('cmd', 'The cmd or type field is required.');
            }
            
            // Ensure params is an associative array (object), not a list
            if (isset($data['params']) && is_array($data['params']) && array_is_list($data['params'])) {
                $validator->errors()->add('params', 'The params field must be an object, not a list.');
            }
            
            // Для set_state требуем state от клиента
            if (($data['cmd'] ?? '') === 'set_state') {
                if (!array_key_exists('state', $data['params'] ?? [])) {
                    $validator->errors()->add('params.state', 'set_state requires params.state (0/1 or true/false)');
                }
            }
        });
    }
}
