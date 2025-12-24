<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class PublishNodeConfigRequest extends FormRequest
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
            // Пока нет дополнительных полей для валидации
            // В будущем можно добавить опции публикации
        ];
    }
}
