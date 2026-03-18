<?php

namespace App\Http\Requests;

use App\Models\GreenhouseAutomationLogicProfile;
use Illuminate\Foundation\Http\FormRequest;

class UpsertGreenhouseAutomationLogicProfileRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        return [
            'mode' => ['required', 'string', 'in:'.implode(',', GreenhouseAutomationLogicProfile::allowedModes())],
            'subsystems' => ['required', 'array'],
            'activate' => ['nullable', 'boolean'],
        ];
    }

    public function withValidator($validator): void
    {
        $validator->after(function ($validator): void {
            $subsystems = $this->input('subsystems');
            if (! is_array($subsystems) || array_is_list($subsystems)) {
                $validator->errors()->add('subsystems', 'The subsystems field must be an object with subsystem keys.');

                return;
            }

            $allowedSubsystems = ['climate'];
            foreach (array_keys($subsystems) as $name) {
                if (! is_string($name)) {
                    continue;
                }

                if (! in_array($name, $allowedSubsystems, true)) {
                    $validator->errors()->add("subsystems.{$name}", "The {$name} subsystem is not supported for greenhouse automation profile.");
                }
            }

            $climate = $subsystems['climate'] ?? null;
            if (! is_array($climate) || array_is_list($climate)) {
                $validator->errors()->add('subsystems.climate', 'The climate subsystem is required.');

                return;
            }

            if (isset($climate['execution']) && (! is_array($climate['execution']) || array_is_list($climate['execution']))) {
                $validator->errors()->add('subsystems.climate.execution', 'The execution field must be an object.');
            }

            if (array_key_exists('targets', $climate)) {
                $validator->errors()->add(
                    'subsystems.climate.targets',
                    'The targets field is not allowed in automation logic profile. Use execution only.'
                );
            }
        });
    }
}
