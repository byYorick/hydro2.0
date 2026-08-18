<?php

namespace App\Http\Requests\SiteWeather;

use Illuminate\Foundation\Http\FormRequest;

class AssignSiteWeatherStationRequest extends FormRequest
{
    public function authorize(): bool
    {
        $user = $this->user();

        return $user !== null && in_array($user->role, ['admin', 'operator', 'agronomist', 'engineer'], true);
    }

    /**
     * @return array<string, mixed>
     */
    public function rules(): array
    {
        return [
            'node_id' => ['required', 'integer', 'exists:nodes,id'],
        ];
    }
}
