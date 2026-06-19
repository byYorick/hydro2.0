<?php

namespace App\Http\Requests;

use App\Services\AutomationScheduler\ManualScheduleService;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class UpdateZoneManualScheduleRequest extends FormRequest
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
            'task_type' => ['sometimes', 'string', Rule::in(ManualScheduleService::ALLOWED_TASK_TYPES)],
            'schedule_kind' => ['sometimes', 'string', Rule::in(ManualScheduleService::ALLOWED_SCHEDULE_KINDS)],
            'time_at' => ['nullable', 'string', 'regex:/^([01]?\d|2[0-3]):([0-5]\d)$/'],
            'interval_sec' => ['nullable', 'integer', 'min:60', 'max:86400'],
            'window_start' => ['nullable', 'string', 'regex:/^([01]?\d|2[0-3]):([0-5]\d)$/'],
            'window_end' => ['nullable', 'string', 'regex:/^([01]?\d|2[0-3]):([0-5]\d)$/'],
            'days_of_week' => ['nullable', 'array'],
            'days_of_week.*' => ['integer', 'min:1', 'max:7'],
            'run_at' => ['nullable', 'date'],
            'payload' => ['nullable', 'array'],
            'payload.duration_sec' => ['nullable', 'integer', 'min:10', 'max:86400'],
            'label' => ['nullable', 'string', 'max:255'],
            'enabled' => ['sometimes', 'boolean'],
        ];
    }
}
