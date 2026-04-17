<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class UpdateZoneAutomationPresetRequest extends FormRequest
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
            'name' => ['sometimes', 'string', 'max:128'],
            'description' => ['nullable', 'string', 'max:2000'],
            'tanks_count' => ['sometimes', 'integer', Rule::in([2, 3])],
            'irrigation_system_type' => [
                'sometimes', 'string',
                Rule::in(['drip_tape', 'drip_emitter', 'ebb_flow', 'nft', 'dwc', 'aeroponics']),
            ],
            'correction_preset_id' => ['nullable', 'integer', 'exists:automation_config_presets,id'],
            'correction_profile' => ['nullable', 'string', Rule::in(['safe', 'balanced', 'aggressive', 'test'])],

            'config' => ['sometimes', 'array'],
            'config.irrigation' => ['sometimes', 'array'],
            'config.irrigation.duration_sec' => ['sometimes', 'integer', 'min:10', 'max:86400'],
            'config.irrigation.interval_sec' => ['sometimes', 'integer', 'min:60', 'max:86400'],
            'config.irrigation.correction_during_irrigation' => ['sometimes', 'boolean'],
            'config.irrigation.correction_slack_sec' => ['sometimes', 'integer', 'min:0', 'max:3600'],

            'config.irrigation_decision' => ['sometimes', 'array'],
            'config.irrigation_decision.strategy' => ['sometimes', 'string', Rule::in(['task', 'smart_soil_v1'])],
            'config.irrigation_decision.config' => ['nullable', 'array'],

            'config.startup' => ['sometimes', 'array'],
            'config.startup.clean_fill_timeout_sec' => ['sometimes', 'integer', 'min:60', 'max:7200'],
            'config.startup.solution_fill_timeout_sec' => ['sometimes', 'integer', 'min:60', 'max:7200'],
            'config.startup.prepare_recirculation_timeout_sec' => ['sometimes', 'integer', 'min:60', 'max:7200'],
            'config.startup.level_poll_interval_sec' => ['sometimes', 'integer', 'min:5', 'max:600'],
            'config.startup.clean_fill_retry_cycles' => ['sometimes', 'integer', 'min:0', 'max:10'],

            'config.climate' => ['nullable', 'array'],
            'config.lighting' => ['nullable', 'array'],
        ];
    }
}
