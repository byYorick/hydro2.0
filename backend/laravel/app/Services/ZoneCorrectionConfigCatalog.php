<?php

namespace App\Services;

use InvalidArgumentException;

class ZoneCorrectionConfigCatalog
{
    public const PHASES = [
        'solution_fill',
        'tank_recirc',
        'irrigation',
    ];

    public static function defaults(): array
    {
        return [
            'controllers' => [
                'ph' => [
                    'mode' => 'cross_coupled_pi_d',
                    'kp' => 0.28,
                    'ki' => 0.015,
                    'kd' => 0.0,
                    'derivative_filter_alpha' => 0.35,
                    'deadband' => 0.04,
                    'max_dose_ml' => 35.0,
                    'min_interval_sec' => 20,
                    'max_integral' => 12.0,
                    'anti_windup' => ['enabled' => true],
                    'overshoot_guard' => ['enabled' => true, 'hard_min' => 4.0, 'hard_max' => 9.0],
                    'no_effect' => ['enabled' => true, 'max_count' => 4],
                    'observe' => [
                        'telemetry_period_sec' => 2,
                        'window_min_samples' => 3,
                        'decision_window_sec' => 8,
                        'observe_poll_sec' => 2,
                        'min_effect_fraction' => 0.15,
                        'stability_max_slope' => 0.04,
                        'no_effect_consecutive_limit' => 4,
                    ],
                ],
                'ec' => [
                    'mode' => 'supervisory_allocator',
                    'kp' => 0.55,
                    'ki' => 0.03,
                    'kd' => 0.0,
                    'derivative_filter_alpha' => 0.35,
                    'deadband' => 0.06,
                    'max_dose_ml' => 80.0,
                    'min_interval_sec' => 25,
                    'max_integral' => 20.0,
                    'anti_windup' => ['enabled' => true],
                    'overshoot_guard' => ['enabled' => true, 'hard_min' => 0.0, 'hard_max' => 10.0],
                    'no_effect' => ['enabled' => true, 'max_count' => 4],
                    'observe' => [
                        'telemetry_period_sec' => 2,
                        'window_min_samples' => 3,
                        'decision_window_sec' => 8,
                        'observe_poll_sec' => 2,
                        'min_effect_fraction' => 0.15,
                        'stability_max_slope' => 0.08,
                        'no_effect_consecutive_limit' => 4,
                    ],
                ],
            ],
            'runtime' => [
                'required_node_type' => 'irrig',
                'clean_fill_timeout_sec' => 1200,
                'solution_fill_timeout_sec' => 900,
                'clean_fill_retry_cycles' => 1,
                'level_switch_on_threshold' => 0.5,
                'clean_max_sensor_label' => 'level_clean_max',
                'clean_min_sensor_label' => 'level_clean_min',
                'solution_max_sensor_label' => 'level_solution_max',
                'solution_min_sensor_label' => 'level_solution_min',
            ],
            'timing' => [
                'sensor_mode_stabilization_time_sec' => 8,
                'stabilization_sec' => 8,
                'telemetry_max_age_sec' => 10,
                'irr_state_max_age_sec' => 30,
                'level_poll_interval_sec' => 10,
            ],
            'dosing' => [
                'solution_volume_l' => 100.0,
                'dose_ec_channel' => 'pump_a',
                'dose_ph_up_channel' => 'pump_base',
                'dose_ph_down_channel' => 'pump_acid',
                'max_ec_dose_ml' => 80.0,
                'max_ph_dose_ml' => 35.0,
                'ec_dosing_mode' => 'single',
            ],
            'retry' => [
                'max_ec_correction_attempts' => 8,
                'max_ph_correction_attempts' => 8,
                'prepare_recirculation_timeout_sec' => 900,
                'prepare_recirculation_correction_slack_sec' => 0,
                'prepare_recirculation_max_attempts' => 4,
                'prepare_recirculation_max_correction_attempts' => 40,
                'telemetry_stale_retry_sec' => 30,
                'decision_window_retry_sec' => 10,
                'low_water_retry_sec' => 60,
            ],
            'tolerance' => [
                'prepare_tolerance' => [
                    'ph_pct' => 5.0,
                    'ec_pct' => 10.0,
                ],
            ],
            'safety' => [
                'safe_mode_on_no_effect' => true,
                'block_on_active_no_effect_alert' => true,
            ],
        ];
    }

    public static function fieldCatalog(): array
    {
        return [
            [
                'key' => 'controllers.ph',
                'label' => 'pH controller',
                'description' => 'Параметры bounded PI/PID для коррекции pH.',
                'advanced_only' => false,
                'fields' => [
                    self::field('controllers.ph.mode', 'Режим pH controller', 'Тип алгоритма pH-контроллера.', 'enum', ['options' => ['cross_coupled_pi_d'], 'readonly' => true]),
                    self::field('controllers.ph.kp', 'Kp', 'Пропорциональная составляющая pH-контроллера.', 'number', ['min' => 0.0, 'max' => 1000.0, 'step' => 0.1]),
                    self::field('controllers.ph.ki', 'Ki', 'Интегральная составляющая pH-контроллера.', 'number', ['min' => 0.0, 'max' => 100.0, 'step' => 0.01]),
                    self::field('controllers.ph.kd', 'Kd', 'Дифференциальная составляющая pH-контроллера.', 'number', ['min' => 0.0, 'max' => 100.0, 'step' => 0.01, 'advanced_only' => true]),
                    self::field('controllers.ph.derivative_filter_alpha', 'Derivative filter alpha', 'Вес нового derivative-сэмпла: 0.0 = максимум сглаживания, 1.0 = без сглаживания.', 'number', ['min' => 0.0, 'max' => 1.0, 'step' => 0.01, 'advanced_only' => true]),
                    self::field('controllers.ph.deadband', 'Deadband', 'Зона без коррекции вокруг целевого окна pH.', 'number', ['min' => 0.0, 'max' => 2.0, 'step' => 0.01]),
                    self::field('controllers.ph.max_dose_ml', 'Max dose ml', 'Максимальная разовая доза pH-коррекции.', 'number', ['min' => 0.001, 'max' => 1000.0, 'step' => 0.1]),
                    self::field('controllers.ph.min_interval_sec', 'Min interval sec', 'Минимальный интервал между pH-дозами.', 'integer', ['min' => 1, 'max' => 3600]),
                    self::field('controllers.ph.max_integral', 'Max integral', 'Ограничение интегральной составляющей для anti-windup.', 'number', ['min' => 0.001, 'max' => 500.0, 'step' => 0.1]),
                    self::field('controllers.ph.anti_windup.enabled', 'Anti-windup', 'Разрешает ограничение интеграла при saturating output.', 'boolean'),
                    self::field('controllers.ph.overshoot_guard.enabled', 'Overshoot guard', 'Останавливает коррекцию при выходе pH за hard-limit.', 'boolean'),
                    self::field('controllers.ph.overshoot_guard.hard_min', 'Overshoot hard min', 'Нижний аварийный предел pH.', 'number', ['min' => 0.0, 'max' => 14.0, 'step' => 0.01]),
                    self::field('controllers.ph.overshoot_guard.hard_max', 'Overshoot hard max', 'Верхний аварийный предел pH.', 'number', ['min' => 0.0, 'max' => 14.0, 'step' => 0.01]),
                    self::field('controllers.ph.no_effect.enabled', 'No-effect guard', 'Контроль обязательного изменения pH после дозы.', 'boolean'),
                    self::field('controllers.ph.no_effect.max_count', 'No-effect max count', 'Сколько подряд неэффективных pH-доз допускается до alert/safe mode.', 'integer', ['min' => 1, 'max' => 10]),
                    self::field('controllers.ph.observe.telemetry_period_sec', 'Telemetry period', 'Ожидаемый период pH telemetry для observe-window.', 'integer', ['min' => 1, 'max' => 300]),
                    self::field('controllers.ph.observe.window_min_samples', 'Window samples', 'Минимум pH samples в окне observe перед decision.', 'integer', ['min' => 2, 'max' => 64]),
                    self::field('controllers.ph.observe.decision_window_sec', 'Decision window', 'Минимальная длина окна наблюдения pH после дозы.', 'integer', ['min' => 1, 'max' => 3600]),
                    self::field('controllers.ph.observe.observe_poll_sec', 'Observe poll', 'Через сколько секунд повторять pH observe-check, если окно ещё не готово.', 'integer', ['min' => 1, 'max' => 300]),
                    self::field('controllers.ph.observe.min_effect_fraction', 'Min effect fraction', 'Минимальная доля ожидаемого pH-эффекта, ниже которой попытка считается no-effect.', 'number', ['min' => 0.01, 'max' => 1.0, 'step' => 0.01]),
                    self::field('controllers.ph.observe.stability_max_slope', 'Stability max slope', 'Максимальный допустимый slope pH-window для признания окна стабильным.', 'number', ['min' => 0.0001, 'max' => 100.0, 'step' => 0.0001]),
                    self::field('controllers.ph.observe.no_effect_consecutive_limit', 'No-effect consecutive', 'Сколько подряд no-effect pH-доз допускается до fail-closed.', 'integer', ['min' => 1, 'max' => 10]),
                ],
            ],
            [
                'key' => 'controllers.ec',
                'label' => 'EC controller',
                'description' => 'Параметры bounded PI/PID для EC supervisory allocator.',
                'advanced_only' => false,
                'fields' => [
                    self::field('controllers.ec.mode', 'Режим EC controller', 'Тип алгоритма EC-контроллера.', 'enum', ['options' => ['supervisory_allocator'], 'readonly' => true]),
                    self::field('controllers.ec.kp', 'Kp', 'Пропорциональная составляющая EC-контроллера.', 'number', ['min' => 0.0, 'max' => 1000.0, 'step' => 0.1]),
                    self::field('controllers.ec.ki', 'Ki', 'Интегральная составляющая EC-контроллера.', 'number', ['min' => 0.0, 'max' => 100.0, 'step' => 0.01]),
                    self::field('controllers.ec.kd', 'Kd', 'Дифференциальная составляющая EC-контроллера.', 'number', ['min' => 0.0, 'max' => 100.0, 'step' => 0.01, 'advanced_only' => true]),
                    self::field('controllers.ec.derivative_filter_alpha', 'Derivative filter alpha', 'Вес нового derivative-сэмпла: 0.0 = максимум сглаживания, 1.0 = без сглаживания.', 'number', ['min' => 0.0, 'max' => 1.0, 'step' => 0.01, 'advanced_only' => true]),
                    self::field('controllers.ec.deadband', 'Deadband', 'Зона без EC-коррекции вокруг целевого окна.', 'number', ['min' => 0.0, 'max' => 5.0, 'step' => 0.01]),
                    self::field('controllers.ec.max_dose_ml', 'Max dose ml', 'Максимальная разовая EC-доза.', 'number', ['min' => 0.001, 'max' => 1000.0, 'step' => 0.1]),
                    self::field('controllers.ec.min_interval_sec', 'Min interval sec', 'Минимальный интервал между EC-дозами.', 'integer', ['min' => 1, 'max' => 3600]),
                    self::field('controllers.ec.max_integral', 'Max integral', 'Ограничение интеграла EC-контроллера.', 'number', ['min' => 0.001, 'max' => 500.0, 'step' => 0.1]),
                    self::field('controllers.ec.anti_windup.enabled', 'Anti-windup', 'Разрешает ограничение интеграла при saturating output.', 'boolean'),
                    self::field('controllers.ec.overshoot_guard.enabled', 'Overshoot guard', 'Останавливает коррекцию при выходе EC за hard-limit.', 'boolean'),
                    self::field('controllers.ec.overshoot_guard.hard_min', 'Overshoot hard min', 'Нижний аварийный предел EC.', 'number', ['min' => 0.0, 'max' => 20.0, 'step' => 0.01]),
                    self::field('controllers.ec.overshoot_guard.hard_max', 'Overshoot hard max', 'Верхний аварийный предел EC.', 'number', ['min' => 0.0, 'max' => 20.0, 'step' => 0.01]),
                    self::field('controllers.ec.no_effect.enabled', 'No-effect guard', 'Контроль обязательного изменения EC после дозы.', 'boolean'),
                    self::field('controllers.ec.no_effect.max_count', 'No-effect max count', 'Сколько подряд неэффективных EC-доз допускается до alert/safe mode.', 'integer', ['min' => 1, 'max' => 10]),
                    self::field('controllers.ec.observe.telemetry_period_sec', 'Telemetry period', 'Ожидаемый период EC telemetry для observe-window.', 'integer', ['min' => 1, 'max' => 300]),
                    self::field('controllers.ec.observe.window_min_samples', 'Window samples', 'Минимум EC samples в окне observe перед decision.', 'integer', ['min' => 2, 'max' => 64]),
                    self::field('controllers.ec.observe.decision_window_sec', 'Decision window', 'Минимальная длина окна наблюдения EC после дозы.', 'integer', ['min' => 1, 'max' => 3600]),
                    self::field('controllers.ec.observe.observe_poll_sec', 'Observe poll', 'Через сколько секунд повторять EC observe-check, если окно ещё не готово.', 'integer', ['min' => 1, 'max' => 300]),
                    self::field('controllers.ec.observe.min_effect_fraction', 'Min effect fraction', 'Минимальная доля ожидаемого EC-эффекта, ниже которой попытка считается no-effect.', 'number', ['min' => 0.01, 'max' => 1.0, 'step' => 0.01]),
                    self::field('controllers.ec.observe.stability_max_slope', 'Stability max slope', 'Максимальный допустимый slope EC-window для признания окна стабильным.', 'number', ['min' => 0.0001, 'max' => 100.0, 'step' => 0.0001]),
                    self::field('controllers.ec.observe.no_effect_consecutive_limit', 'No-effect consecutive', 'Сколько подряд no-effect EC-доз допускается до fail-closed.', 'integer', ['min' => 1, 'max' => 10]),
                ],
            ],
            [
                'key' => 'runtime',
                'label' => 'Two-tank runtime',
                'description' => 'Параметры two-tank startup/runtime path, которые раньше жили в diagnostics.execution.startup.',
                'advanced_only' => false,
                'fields' => [
                    self::field('runtime.required_node_type', 'Required node type', 'Тип основного irrigation node для two-tank runtime.', 'string', ['max_length' => 64]),
                    self::field('runtime.clean_fill_timeout_sec', 'Clean fill timeout', 'Таймаут стадии clean_fill.', 'integer', ['min' => 30, 'max' => 86400]),
                    self::field('runtime.solution_fill_timeout_sec', 'Solution fill timeout', 'Таймаут стадии solution_fill.', 'integer', ['min' => 30, 'max' => 86400]),
                    self::field('runtime.clean_fill_retry_cycles', 'Clean fill retry cycles', 'Сколько retry clean_fill допускается до fail.', 'integer', ['min' => 0, 'max' => 20]),
                    self::field('runtime.level_switch_on_threshold', 'Level switch threshold', 'Порог telemetry для срабатывания level switch.', 'number', ['min' => 0.0, 'max' => 1.0, 'step' => 0.01]),
                    self::field('runtime.clean_max_sensor_label', 'Clean max sensor label', 'Label верхнего датчика clean tank.', 'string', ['max_length' => 128, 'advanced_only' => true]),
                    self::field('runtime.clean_min_sensor_label', 'Clean min sensor label', 'Label нижнего датчика clean tank.', 'string', ['max_length' => 128, 'advanced_only' => true]),
                    self::field('runtime.solution_max_sensor_label', 'Solution max sensor label', 'Label верхнего датчика solution tank.', 'string', ['max_length' => 128, 'advanced_only' => true]),
                    self::field('runtime.solution_min_sensor_label', 'Solution min sensor label', 'Label нижнего датчика solution tank.', 'string', ['max_length' => 128, 'advanced_only' => true]),
                ],
            ],
            [
                'key' => 'timing',
                'label' => 'Timing',
                'description' => 'Тайминги stage-level стабилизации и freshness telemetry. Observe-loop для PH/EC задаётся в controllers.*.observe и process calibration.',
                'advanced_only' => false,
                'fields' => [
                    self::field('timing.sensor_mode_stabilization_time_sec', 'Sensor mode stabilization', 'Ожидание после включения sensor mode.', 'integer', ['min' => 0, 'max' => 3600]),
                    self::field('timing.stabilization_sec', 'Correction stabilization', 'Ожидание перед первым corr_check.', 'integer', ['min' => 0, 'max' => 3600]),
                    self::field('timing.telemetry_max_age_sec', 'Telemetry max age', 'Максимальный возраст PH/EC telemetry для correction runtime.', 'integer', ['min' => 5, 'max' => 3600]),
                    self::field('timing.irr_state_max_age_sec', 'IRR state max age', 'Максимальный возраст снимка storage_state.', 'integer', ['min' => 5, 'max' => 3600, 'advanced_only' => true]),
                    self::field('timing.level_poll_interval_sec', 'Level poll interval', 'Интервал повторной проверки level sensors.', 'integer', ['min' => 5, 'max' => 3600, 'advanced_only' => true]),
                ],
            ],
            [
                'key' => 'dosing',
                'label' => 'Dosing',
                'description' => 'Каналы актуаторов и stage-level clamps. Planner в observation-driven режиме требует process calibration gain-и.',
                'advanced_only' => false,
                'fields' => [
                    self::field('dosing.solution_volume_l', 'Solution volume', 'Расчётный объём раствора для allocator/clamp расчётов.', 'number', ['min' => 1.0, 'max' => 10000.0, 'step' => 0.1]),
                    self::field('dosing.max_ec_dose_ml', 'Max EC dose clamp', 'Жёсткий верхний clamp EC-дозы до преобразования в pump pulse.', 'number', ['min' => 0.1, 'max' => 1000.0, 'step' => 0.1, 'advanced_only' => true]),
                    self::field('dosing.max_ph_dose_ml', 'Max pH dose clamp', 'Жёсткий верхний clamp pH-дозы до преобразования в pump pulse.', 'number', ['min' => 0.1, 'max' => 1000.0, 'step' => 0.1, 'advanced_only' => true]),
                    self::field('dosing.dose_ec_channel', 'EC channel', 'Имя актуатора EC-коррекции.', 'string', ['max_length' => 64, 'advanced_only' => true]),
                    self::field('dosing.dose_ph_up_channel', 'pH up channel', 'Имя актуатора pH-up.', 'string', ['max_length' => 64, 'advanced_only' => true]),
                    self::field('dosing.dose_ph_down_channel', 'pH down channel', 'Имя актуатора pH-down.', 'string', ['max_length' => 64, 'advanced_only' => true]),
                    self::field(
                        'dosing.ec_dosing_mode',
                        'EC dosing mode',
                        'Single = одна общая EC-помпа. Multi-parallel = параллельные помпы на компоненты (NPK/A/B). Multi-sequential = sequential multi-pump (legacy). См. recipe ec_component_ratios.',
                        'enum',
                        ['options' => ['single', 'multi_parallel', 'multi_sequential'], 'advanced_only' => true]
                    ),
                ],
            ],
            [
                'key' => 'retry',
                'label' => 'Retry and windows',
                'description' => 'Лимиты correction-loop и recirculation timeout windows.',
                'advanced_only' => false,
                'fields' => [
                    self::field('retry.max_ec_correction_attempts', 'Max EC attempts', 'Лимит EC-дозировок в correction cycle.', 'integer', ['min' => 1, 'max' => 500]),
                    self::field('retry.max_ph_correction_attempts', 'Max pH attempts', 'Лимит pH-дозировок в correction cycle.', 'integer', ['min' => 1, 'max' => 500]),
                    self::field('retry.prepare_recirculation_timeout_sec', 'Recirculation timeout', 'Длительность одного окна recirculation before retry.', 'integer', ['min' => 30, 'max' => 7200]),
                    self::field(
                        'retry.prepare_recirculation_correction_slack_sec',
                        'Recirculation correction slack',
                        'Доп. секунды к дедлайну prepare_recirculation_check для inline-коррекции (AE по умолчанию 900; 0 = жёстко по timeout).',
                        'integer',
                        ['min' => 0, 'max' => 7200, 'advanced_only' => true]
                    ),
                    self::field('retry.prepare_recirculation_max_attempts', 'Recirculation max windows', 'Сколько timeout-window допускается до alert/stop.', 'integer', ['min' => 1, 'max' => 10]),
                    self::field(
                        'retry.prepare_recirculation_max_correction_attempts',
                        'Recirculation correction cap',
                        'Верхний guard для correction loop внутри одного recirculation window.',
                        'integer',
                        ['min' => 1, 'max' => 500, 'advanced_only' => true]
                    ),
                    self::field(
                        'retry.telemetry_stale_retry_sec',
                        'Telemetry stale retry',
                        'Через сколько секунд повторять corr_check/corr_wait, если telemetry временно stale/unavailable.',
                        'integer',
                        ['min' => 1, 'max' => 3600, 'advanced_only' => true]
                    ),
                    self::field(
                        'retry.decision_window_retry_sec',
                        'Decision window retry',
                        'Через сколько секунд повторять corr_check, если decision-window ещё не готово или содержит non-finite value.',
                        'integer',
                        ['min' => 1, 'max' => 3600, 'advanced_only' => true]
                    ),
                    self::field(
                        'retry.low_water_retry_sec',
                        'Low water retry',
                        'Через сколько секунд повторять corr_check, если correction временно заблокирован по low-water guard.',
                        'integer',
                        ['min' => 1, 'max' => 3600, 'advanced_only' => true]
                    ),
                ],
            ],
            [
                'key' => 'tolerance',
                'label' => 'Tolerance',
                'description' => 'Fallback-допуски, когда explicit PH/EC window не задана phase-targets.',
                'advanced_only' => false,
                'fields' => [
                    self::field('tolerance.prepare_tolerance.ph_pct', 'Prepare pH tolerance %', 'Fallback tolerance для pH при отсутствии explicit phase window.', 'number', ['min' => 0.1, 'max' => 100.0, 'step' => 0.1]),
                    self::field('tolerance.prepare_tolerance.ec_pct', 'Prepare EC tolerance %', 'Fallback tolerance для EC при отсутствии explicit phase window.', 'number', ['min' => 0.1, 'max' => 100.0, 'step' => 0.1]),
                ],
            ],
            [
                'key' => 'safety',
                'label' => 'Safety',
                'description' => 'Политики safe mode и блокировки коррекции после критических предупреждений.',
                'advanced_only' => true,
                'fields' => [
                    self::field('safety.safe_mode_on_no_effect', 'Safe mode on no-effect', 'После превышения no-effect count переводить correction в fail-closed режим.', 'boolean'),
                    self::field('safety.block_on_active_no_effect_alert', 'Block on active alert', 'Блокировать automatic correction, пока alert no-effect не ack/resolved.', 'boolean'),
                ],
            ],
        ];
    }

    public static function merge(array $base, array $override): array
    {
        foreach ($override as $key => $value) {
            // Empty JSON objects are decoded as [] in PHP; for object-like branches this means
            // "no override", not "erase the entire subtree".
            if (
                $value === []
                && isset($base[$key])
                && is_array($base[$key])
                && ! array_is_list($base[$key])
            ) {
                continue;
            }

            if (is_array($value) && isset($base[$key]) && is_array($base[$key]) && ! array_is_list($value) && ! array_is_list($base[$key])) {
                $base[$key] = self::merge($base[$key], $value);
                continue;
            }

            $base[$key] = $value;
        }

        return $base;
    }

    public static function diff(array $base, array $target): array
    {
        $result = [];
        foreach ($target as $key => $value) {
            if (! array_key_exists($key, $base)) {
                $result[$key] = $value;
                continue;
            }

            $baseValue = $base[$key];
            if (
                is_array($value) && is_array($baseValue)
                && ! array_is_list($value) && ! array_is_list($baseValue)
            ) {
                $nested = self::diff($baseValue, $value);
                if ($nested !== []) {
                    $result[$key] = $nested;
                }
                continue;
            }

            if ($value !== $baseValue) {
                $result[$key] = $value;
            }
        }

        return $result;
    }

    public static function validateFragment(array $fragment, bool $allowPartial = true, string $prefix = ''): void
    {
        if ($fragment === []) {
            return;
        }

        if (array_is_list($fragment)) {
            throw new InvalidArgumentException(($prefix ?: 'config').' должен быть объектом.');
        }

        foreach ($fragment as $key => $value) {
            $path = $prefix === '' ? (string) $key : "{$prefix}.{$key}";
            if (! self::isKnownPath($path)) {
                throw new InvalidArgumentException("Поле {$path} не поддерживается current correction config contract.");
            }

            if (self::isLeafPath($path)) {
                self::validateLeaf($path, $value);
                continue;
            }

            if (! is_array($value) || array_is_list($value)) {
                throw new InvalidArgumentException("Раздел {$path} должен быть объектом.");
            }

            self::validateFragment($value, $allowPartial, $path);
        }

        if (! $allowPartial) {
            $default = self::defaultBranch($prefix);
            self::validateRequiredBranches($default, $fragment, $prefix);
        }
    }

    public static function defaultResolvedConfig(): array
    {
        $base = self::defaults();
        return [
            'base' => $base,
            'phases' => [
                'solution_fill' => $base,
                'tank_recirc' => $base,
                'irrigation' => $base,
            ],
            'meta' => [
                'preset_slug' => null,
                'preset_name' => null,
            ],
        ];
    }

    public static function validateResolvedConfig(array $resolved): void
    {
        $base = $resolved['base'] ?? null;
        if (! is_array($base) || array_is_list($base)) {
            throw new InvalidArgumentException('resolved_config.base должен быть объектом.');
        }
        self::validateFragment($base, true);
        self::validateRequiredBranches(self::defaults(), $base, 'resolved_config.base');

        $phases = $resolved['phases'] ?? null;
        if (! is_array($phases) || array_is_list($phases)) {
            throw new InvalidArgumentException('resolved_config.phases должен быть объектом.');
        }

        foreach (self::PHASES as $phase) {
            $phaseConfig = $phases[$phase] ?? null;
            if (! is_array($phaseConfig) || array_is_list($phaseConfig)) {
                throw new InvalidArgumentException("resolved_config.phases.{$phase} должен быть объектом.");
            }
            self::validateFragment($phaseConfig, true);
            self::validateRequiredBranches(self::defaults(), $phaseConfig, "resolved_config.phases.{$phase}");
        }
    }

    private static function field(string $path, string $label, string $description, string $type, array $extra = []): array
    {
        return array_merge([
            'path' => $path,
            'label' => $label,
            'description' => $description,
            'type' => $type,
        ], $extra);
    }

    private static function flattenedFields(): array
    {
        static $fields = null;
        if ($fields !== null) {
            return $fields;
        }

        $fields = [];
        foreach (self::fieldCatalog() as $section) {
            foreach ($section['fields'] as $field) {
                $fields[$field['path']] = $field;
            }
        }

        return $fields;
    }

    private static function isKnownPath(string $path): bool
    {
        if (self::isLeafPath($path)) {
            return true;
        }

        $needle = "{$path}.";
        foreach (array_keys(self::flattenedFields()) as $candidate) {
            if (str_starts_with($candidate, $needle)) {
                return true;
            }
        }

        return false;
    }

    private static function isLeafPath(string $path): bool
    {
        return array_key_exists($path, self::flattenedFields());
    }

    private static function validateLeaf(string $path, mixed $value): void
    {
        $field = self::flattenedFields()[$path];
        $type = $field['type'];

        if ($type === 'boolean') {
            if (! is_bool($value)) {
                throw new InvalidArgumentException("Поле {$path} должно быть boolean.");
            }
            return;
        }

        if ($type === 'enum') {
            if (! is_string($value) || ! in_array($value, $field['options'], true)) {
                throw new InvalidArgumentException("Поле {$path} должно быть одним из: ".implode(', ', $field['options']));
            }
            return;
        }

        if ($type === 'string') {
            if (! is_string($value) || trim($value) === '') {
                throw new InvalidArgumentException("Поле {$path} должно быть непустой строкой.");
            }
            if (isset($field['max_length']) && mb_strlen($value) > (int) $field['max_length']) {
                throw new InvalidArgumentException("Поле {$path} превышает максимальную длину {$field['max_length']}.");
            }
            return;
        }

        if ($type === 'integer') {
            if (! is_int($value)) {
                throw new InvalidArgumentException("Поле {$path} должно быть integer.");
            }
            if (isset($field['min']) && $value < $field['min']) {
                throw new InvalidArgumentException("Поле {$path} должно быть >= {$field['min']}.");
            }
            if (isset($field['max']) && $value > $field['max']) {
                throw new InvalidArgumentException("Поле {$path} должно быть <= {$field['max']}.");
            }
            return;
        }

        if (! is_numeric($value)) {
            throw new InvalidArgumentException("Поле {$path} должно быть числом.");
        }

        $numeric = (float) $value;
        if (isset($field['min']) && $numeric < (float) $field['min']) {
            throw new InvalidArgumentException("Поле {$path} должно быть >= {$field['min']}.");
        }
        if (isset($field['max']) && $numeric > (float) $field['max']) {
            throw new InvalidArgumentException("Поле {$path} должно быть <= {$field['max']}.");
        }
    }

    private static function validateRequiredBranches(array $defaults, array $fragment, string $prefix): void
    {
        foreach ($defaults as $key => $defaultValue) {
            $path = $prefix === '' ? (string) $key : "{$prefix}.{$key}";
            if (! array_key_exists($key, $fragment)) {
                throw new InvalidArgumentException("Поле {$path} обязательно.");
            }

            if (is_array($defaultValue) && ! array_is_list($defaultValue) && ! self::isLeafPath($path)) {
                if (! is_array($fragment[$key]) || array_is_list($fragment[$key])) {
                    throw new InvalidArgumentException("Раздел {$path} должен быть объектом.");
                }
                self::validateRequiredBranches($defaultValue, $fragment[$key], $path);
            }
        }
    }

    private static function defaultBranch(string $prefix): array
    {
        if ($prefix === '') {
            return self::defaults();
        }

        $current = self::defaults();
        foreach (explode('.', $prefix) as $segment) {
            if (! is_array($current) || ! array_key_exists($segment, $current) || ! is_array($current[$segment])) {
                return [];
            }
            $current = $current[$segment];
        }

        return $current;
    }
}
