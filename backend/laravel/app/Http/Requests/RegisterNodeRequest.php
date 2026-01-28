<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class RegisterNodeRequest extends FormRequest
{
    /**
     * Determine if the user is authorized to make this request.
     */
    public function authorize(): bool
    {
        return true; // Авторизация через токен проверяется в контроллере
    }

    /**
     * Get the validation rules that apply to the request.
     */
    public function rules(): array
    {
        // Проверяем, это node_hello или обычная регистрация
        if ($this->has('message_type') && $this->input('message_type') === 'node_hello') {
            return [
                'message_type' => ['required', 'string', 'in:node_hello'],
                'hardware_id' => ['required', 'string', 'max:128'],
                'node_type' => ['nullable', 'string', 'max:64'],
                'fw_version' => ['nullable', 'string', 'max:64'],
                'hardware_revision' => ['nullable', 'string', 'max:64'],
                'capabilities' => ['nullable', 'array'],
                'provisioning_meta' => ['nullable', 'array'],
            ];
        }
        
        // Обычная регистрация через API
        return [
            'node_uid' => ['required', 'string', 'max:64'],
            'zone_uid' => ['nullable', 'string', 'max:64'],
            'firmware_version' => ['nullable', 'string', 'max:64'],
            'hardware_revision' => ['nullable', 'string', 'max:64'],
            'hardware_id' => ['nullable', 'string', 'max:128'],
            'name' => ['nullable', 'string', 'max:255'],
            'type' => ['nullable', 'string', 'max:64'],
        ];
    }
}
