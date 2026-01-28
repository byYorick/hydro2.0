<?php

namespace App\Http\Requests\Internal;

use Illuminate\Foundation\Http\FormRequest;

class TelemetryBatchRequest extends FormRequest
{
    /**
     * Determine if the user is authorized to make this request.
     */
    public function authorize(): bool
    {
        return true;
    }

    /**
     * Get the validation rules that apply to the request.
     *
     * @return array<string, \Illuminate\Contracts\Validation\ValidationRule|array<mixed>|string>
     */
    public function rules(): array
    {
        return [
            'updates' => ['required', 'array', 'min:1', 'max:'.config('realtime.telemetry_batch_max_updates')],
            'updates.*.zone_id' => ['required', 'integer', 'min:1'],
            'updates.*.node_id' => ['required', 'integer', 'min:1'],
            'updates.*.channel' => ['nullable', 'string', 'max:64'],
            'updates.*.metric_type' => ['required', 'string', 'max:64'],
            'updates.*.value' => ['required', 'numeric'],
            'updates.*.timestamp' => ['required', 'integer'],
        ];
    }
}
