<?php

namespace App\Http\Requests;

use App\Models\ZoneAutomationLogicProfile;
use Illuminate\Foundation\Http\FormRequest;

class UpsertZoneAutomationLogicProfileRequest extends FormRequest
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
     */
    public function rules(): array
    {
        return [
            'mode' => ['required', 'string', 'in:'.implode(',', ZoneAutomationLogicProfile::allowedModes())],
            'subsystems' => ['required', 'array'],
            'activate' => ['nullable', 'boolean'],
        ];
    }

    /**
     * Configure the validator instance.
     */
    public function withValidator($validator): void
    {
        $validator->after(function ($validator): void {
            $subsystems = $this->input('subsystems');
            if (!is_array($subsystems) || array_is_list($subsystems)) {
                $validator->errors()->add('subsystems', 'The subsystems field must be an object with subsystem keys.');
                return;
            }

            foreach (['ph', 'ec', 'irrigation'] as $requiredSubsystem) {
                $subsystem = $subsystems[$requiredSubsystem] ?? null;
                if (!is_array($subsystem)) {
                    $validator->errors()->add("subsystems.{$requiredSubsystem}", "The {$requiredSubsystem} subsystem is required.");
                    continue;
                }

                if (($subsystem['enabled'] ?? null) !== true) {
                    $validator->errors()->add("subsystems.{$requiredSubsystem}.enabled", 'Required subsystem must be enabled=true.');
                }
            }

            foreach ($subsystems as $name => $subsystem) {
                if (!is_array($subsystem)) {
                    $validator->errors()->add("subsystems.{$name}", "The {$name} subsystem must be an object.");
                    continue;
                }

                if (array_is_list($subsystem)) {
                    $validator->errors()->add("subsystems.{$name}", "The {$name} subsystem must be an object.");
                }

                if (isset($subsystem['execution']) && !is_array($subsystem['execution'])) {
                    $validator->errors()->add("subsystems.{$name}.execution", 'The execution field must be an object.');
                }

                if (array_key_exists('targets', $subsystem)) {
                    $validator->errors()->add(
                        "subsystems.{$name}.targets",
                        'The targets field is not allowed in automation logic profile. Use execution only.'
                    );
                }
            }
        });
    }
}
