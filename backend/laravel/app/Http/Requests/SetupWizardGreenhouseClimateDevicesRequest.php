<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class SetupWizardGreenhouseClimateDevicesRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        return [
            'greenhouse_id' => ['required', 'integer', 'exists:greenhouses,id'],
            'enabled' => ['nullable', 'boolean'],
            'climate_sensors' => ['nullable', 'array'],
            'climate_sensors.*' => ['integer', 'exists:nodes,id'],
            'weather_station_sensors' => ['nullable', 'array'],
            'weather_station_sensors.*' => ['integer', 'exists:nodes,id'],
            'vent_actuators' => ['nullable', 'array'],
            'vent_actuators.*' => ['integer', 'exists:nodes,id'],
            'fan_actuators' => ['nullable', 'array'],
            'fan_actuators.*' => ['integer', 'exists:nodes,id'],
        ];
    }
}
