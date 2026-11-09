<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class StoreZoneEstopRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    /**
     * @return array<string, mixed>
     */
    public function rules(): array
    {
        return [
            'action' => ['required', 'string', 'in:engage,release'],
            'reason' => ['nullable', 'string', 'max:500'],
        ];
    }

    public function withValidator($validator): void
    {
        $validator->after(function ($validator): void {
            if ($this->input('action') !== 'release') {
                return;
            }
            $reason = trim((string) $this->input('reason', ''));
            if (mb_strlen($reason) < 3) {
                $validator->errors()->add('reason', 'Для снятия E-STOP укажите причину (не короче 3 символов).');
            }
        });
    }
}
