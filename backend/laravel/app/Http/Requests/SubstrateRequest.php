<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class SubstrateRequest extends FormRequest
{
    public function authorize(): bool
    {
        return $this->user() !== null;
    }

    public function rules(): array
    {
        $substrateId = $this->route('substrate')?->id;

        return [
            'code' => [
                'required', 'string', 'max:64',
                Rule::unique('substrates', 'code')->ignore($substrateId),
            ],
            'name' => ['required', 'string', 'max:128'],
            'components' => ['required', 'array', 'min:1'],
            'components.*.name' => ['required', 'string', 'max:64'],
            'components.*.label' => ['nullable', 'string', 'max:128'],
            'components.*.ratio_pct' => ['required', 'numeric', 'min:0', 'max:100'],
            'applicable_systems' => ['nullable', 'array'],
            'applicable_systems.*' => ['string', Rule::in(['drip_tape', 'drip_emitter', 'ebb_flow', 'nft', 'dwc', 'aeroponics'])],
            'notes' => ['nullable', 'string', 'max:2000'],
        ];
    }

    public function withValidator($validator): void
    {
        $validator->after(function ($v): void {
            $components = $this->input('components', []);
            if (! is_array($components) || count($components) === 0) {
                return;
            }
            $sum = 0.0;
            foreach ($components as $c) {
                if (is_array($c) && isset($c['ratio_pct']) && is_numeric($c['ratio_pct'])) {
                    $sum += (float) $c['ratio_pct'];
                }
            }
            if (abs($sum - 100.0) > 0.01) {
                $v->errors()->add('components', 'Сумма долей компонентов должна быть 100%.');
            }
        });
    }
}
