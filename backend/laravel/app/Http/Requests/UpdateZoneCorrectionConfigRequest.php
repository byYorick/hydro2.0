<?php

namespace App\Http\Requests;

use App\Services\ZoneCorrectionConfigCatalog;
use Illuminate\Foundation\Http\FormRequest;

class UpdateZoneCorrectionConfigRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        return [
            'preset_id' => ['nullable', 'integer', 'exists:zone_correction_presets,id'],
            'base_config' => ['nullable', 'array'],
            'phase_overrides' => ['nullable', 'array'],
            'phase_overrides.solution_fill' => ['sometimes', 'array'],
            'phase_overrides.tank_recirc' => ['sometimes', 'array'],
            'phase_overrides.irrigation' => ['sometimes', 'array'],
        ];
    }

    public function withValidator($validator): void
    {
        $validator->after(function ($validator): void {
            $phaseOverrides = $this->input('phase_overrides');
            if (is_array($phaseOverrides) && ! array_is_list($phaseOverrides)) {
                foreach (array_keys($phaseOverrides) as $phase) {
                    if (! in_array($phase, ZoneCorrectionConfigCatalog::PHASES, true)) {
                        $validator->errors()->add(
                            "phase_overrides.{$phase}",
                            'Unsupported phase override.'
                        );
                    }
                }
            }
        });
    }
}
