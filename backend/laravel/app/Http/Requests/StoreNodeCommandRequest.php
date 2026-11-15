<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class StoreNodeCommandRequest extends FormRequest
{
    /**
     * Команды и параметры, которые принимает ручной node API.
     * Источник — MQTT_SPEC_FULL §7 и COMMAND_VALIDATION_ENGINE.
     *
     * @var array<string, list<string>>
     */
    public const ALLOWED_PARAMS = [
        'run_pump' => ['duration_ms'],
        'dose' => ['ml'],
        'set_relay' => ['state', 'duration_ms', 'timeout_ms', 'stage'],
        'set_state' => ['state', 'duration_ms', 'timeout_ms', 'stage'],
        'set_pwm' => ['duty', 'value'],
        'set_position' => ['position_pct', 'max_step_pct'],
        'calibrate' => ['type', 'stage', 'known_ph', 'tds_value'],
        'test_sensor' => [],
        'restart' => [],
        'state' => [],
    ];

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
            'type' => ['nullable', 'string', 'max:64'],
            'cmd' => ['nullable', 'string', 'max:64'],
            'channel' => ['nullable', 'string', 'max:128'],
            'params' => ['nullable', 'array'],
        ];
    }

    public function withValidator($validator): void
    {
        $validator->after(function ($validator): void {
            $data = $this->all();
            $cmd = $data['cmd'] ?? $data['type'] ?? null;
            if (! is_string($cmd) || trim($cmd) === '') {
                $validator->errors()->add('cmd', 'The cmd or type field is required.');

                return;
            }

            $cmd = strtolower(trim($cmd));
            if (! array_key_exists($cmd, self::ALLOWED_PARAMS)) {
                $validator->errors()->add('cmd', 'Команда не входит в допустимый список.');

                return;
            }

            $params = $data['params'] ?? [];
            if ($params === null) {
                $params = [];
            }
            if (! is_array($params)) {
                $validator->errors()->add('params', 'The params field must be an object, not a list.');

                return;
            }
            if (array_is_list($params)) {
                if (count($params) > 0) {
                    $validator->errors()->add('params', 'The params field must be an object, not a list.');

                    return;
                }
                $params = [];
            }

            $allowed = self::ALLOWED_PARAMS[$cmd];
            foreach (array_keys($params) as $key) {
                if (! in_array((string) $key, $allowed, true)) {
                    $validator->errors()->add('params.'.$key, 'Параметр не допускается для этой команды.');
                }
            }

            if ($validator->errors()->isNotEmpty()) {
                return;
            }

            if (in_array($cmd, ['set_state', 'set_relay'], true) && ! array_key_exists('state', $params)) {
                $validator->errors()->add('params.state', 'set_state/set_relay requires params.state (0/1 or true/false)');
            }

            if ($cmd === 'dose' && (! isset($params['ml']) || ! is_numeric($params['ml']) || (float) $params['ml'] <= 0)) {
                $validator->errors()->add('params.ml', 'dose требует положительный params.ml.');
            }

            if ($cmd === 'run_pump' && (! isset($params['duration_ms']) || ! is_numeric($params['duration_ms']) || (int) $params['duration_ms'] <= 0)) {
                $validator->errors()->add('params.duration_ms', 'run_pump требует положительный params.duration_ms.');
            }

            if ($cmd === 'set_pwm' && ! isset($params['duty']) && ! isset($params['value'])) {
                $validator->errors()->add('params.duty', 'set_pwm требует params.duty или params.value.');
            }

            if ($cmd === 'set_position' && (! isset($params['position_pct']) || ! is_numeric($params['position_pct']))) {
                $validator->errors()->add('params.position_pct', 'set_position требует числовой params.position_pct.');
            }

            if ($cmd === 'calibrate' && ! isset($params['type']) && ! isset($params['stage'])) {
                $validator->errors()->add('params.stage', 'calibrate требует params.type или params.stage.');
            }
        });
    }
}
