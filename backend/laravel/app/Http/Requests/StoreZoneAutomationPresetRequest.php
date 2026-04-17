<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class StoreZoneAutomationPresetRequest extends FormRequest
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
            'name' => ['required', 'string', 'max:128'],
            'description' => ['nullable', 'string', 'max:2000'],
            'tanks_count' => ['required', 'integer', Rule::in([2, 3])],
            'irrigation_system_type' => [
                'required', 'string',
                Rule::in(['drip_tape', 'drip_emitter', 'ebb_flow', 'nft', 'dwc', 'aeroponics']),
            ],
            'correction_preset_id' => ['nullable', 'integer', 'exists:automation_config_presets,id'],
            'correction_profile' => ['nullable', 'string', Rule::in(['safe', 'balanced', 'aggressive', 'test'])],

            'config' => ['required', 'array'],
            'config.irrigation' => ['required', 'array'],
            'config.irrigation.duration_sec' => ['required', 'integer', 'min:10', 'max:86400'],
            'config.irrigation.interval_sec' => ['required', 'integer', 'min:60', 'max:86400'],
            'config.irrigation.correction_during_irrigation' => ['required', 'boolean'],
            'config.irrigation.correction_slack_sec' => ['required', 'integer', 'min:0', 'max:3600'],

            'config.irrigation_decision' => ['required', 'array'],
            'config.irrigation_decision.strategy' => ['required', 'string', Rule::in(['task', 'smart_soil_v1'])],
            'config.irrigation_decision.config' => ['nullable', 'array'],
            'config.irrigation_decision.config.lookback_sec' => ['nullable', 'integer', 'min:60', 'max:86400'],
            'config.irrigation_decision.config.min_samples' => ['nullable', 'integer', 'min:1', 'max:100'],
            'config.irrigation_decision.config.stale_after_sec' => ['nullable', 'integer', 'min:60', 'max:86400'],
            'config.irrigation_decision.config.hysteresis_pct' => ['nullable', 'numeric', 'min:0', 'max:50'],
            'config.irrigation_decision.config.spread_alert_threshold_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],

            'config.startup' => ['required', 'array'],
            'config.startup.clean_fill_timeout_sec' => ['required', 'integer', 'min:60', 'max:7200'],
            'config.startup.solution_fill_timeout_sec' => ['required', 'integer', 'min:60', 'max:7200'],
            'config.startup.prepare_recirculation_timeout_sec' => ['required', 'integer', 'min:60', 'max:7200'],
            'config.startup.level_poll_interval_sec' => ['required', 'integer', 'min:5', 'max:600'],
            'config.startup.clean_fill_retry_cycles' => ['required', 'integer', 'min:0', 'max:10'],

            'config.climate' => ['nullable', 'array'],
            'config.lighting' => ['nullable', 'array'],
        ];
    }
}
