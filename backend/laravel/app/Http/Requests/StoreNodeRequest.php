<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class StoreNodeRequest extends FormRequest
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
            'zone_id' => ['nullable', 'integer', 'exists:zones,id'],
            'uid' => ['required', 'string', 'max:64', 'unique:nodes,uid'],
            'name' => ['nullable', 'string', 'max:255'],
            'type' => ['nullable', 'string', 'max:64'],
            'fw_version' => ['nullable', 'string', 'max:64'],
            'status' => ['nullable', 'string', 'max:32'],
            'config' => ['nullable', 'array'],
        ];
    }
}
