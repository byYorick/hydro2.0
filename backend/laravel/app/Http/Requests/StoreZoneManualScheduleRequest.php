<?php

namespace App\Http\Requests;

use App\Services\AutomationScheduler\ManualScheduleService;
use App\Services\AutomationScheduler\ScheduleSpecHelper;
use App\Services\AutomationScheduler\SchedulerRuntimeHelper;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;
use Illuminate\Validation\Validator;

class StoreZoneManualScheduleRequest extends FormRequest
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
        return $this->baseRules(requireFutureRunAt: true);
    }

    public function withValidator(Validator $validator): void
    {
        $validator->after(function (Validator $validator): void {
            if ($this->input('schedule_kind') !== 'once') {
                return;
            }

            $runAt = ScheduleSpecHelper::parseRunAt($this->input('run_at'));
            if ($runAt === null || ! $runAt->gt(SchedulerRuntimeHelper::nowUtc())) {
                $validator->errors()->add('run_at', 'Для schedule_kind=once run_at должен быть в будущем (UTC).');
            }
        });
    }

    /**
     * @return array<string, mixed>
     */
    protected function baseRules(bool $requireFutureRunAt = false): array
    {
        return [
            'task_type' => ['required', 'string', Rule::in(ManualScheduleService::ALLOWED_TASK_TYPES)],
            'schedule_kind' => ['required', 'string', Rule::in(ManualScheduleService::ALLOWED_SCHEDULE_KINDS)],
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
