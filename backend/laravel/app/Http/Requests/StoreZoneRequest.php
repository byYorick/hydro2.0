<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class StoreZoneRequest extends FormRequest
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
            'greenhouse_id' => ['required', 'integer', 'exists:greenhouses,id'],
            'preset_id' => ['nullable', 'integer', 'exists:presets,id'],
            'name' => ['required', 'string', 'max:255'],
            'description' => ['nullable', 'string', 'max:1000'],
            'status' => ['nullable', 'string', 'in:active,inactive,maintenance'],
            'hardware_profile' => ['nullable', 'array'],
            'capabilities' => ['nullable', 'array'],
            'settings' => ['nullable', 'array'],
        ];
    }
}

