<?php

namespace App\Services;

use InvalidArgumentException;

class SystemAutomationSettingsCatalog
{
    private const FIELD_CATALOG = [
        'pump_calibration' => [
            [
                'key' => 'pump_calibration',
                'label' => 'Калибровка насосов',
                'description' => 'Системные пороги ручной и runtime pump calibration.',
                'fields' => [
                    ['path' => 'ml_per_sec_min', 'label' => 'Min ml/sec', 'description' => 'Минимальная допустимая скорость насоса.', 'type' => 'number', 'min' => 0.001, 'max' => 1.0, 'step' => 0.001],
                    ['path' => 'ml_per_sec_max', 'label' => 'Max ml/sec', 'description' => 'Максимальная допустимая скорость насоса.', 'type' => 'number', 'min' => 5.0, 'max' => 200.0, 'step' => 0.1],
                    ['path' => 'min_dose_ms', 'label' => 'Min dose ms', 'description' => 'Минимальный эффективный импульс дозирования.', 'type' => 'integer', 'min' => 10, 'max' => 500],
                    ['path' => 'calibration_duration_min_sec', 'label' => 'Calibration min sec', 'description' => 'Минимальная длительность pump run для калибровки.', 'type' => 'integer', 'min' => 1, 'max' => 10],
                    ['path' => 'calibration_duration_max_sec', 'label' => 'Calibration max sec', 'description' => 'Максимальная длительность pump run для калибровки.', 'type' => 'integer', 'min' => 30, 'max' => 600],
                    ['path' => 'quality_score_basic', 'label' => 'Quality basic', 'description' => 'Score для базовой калибровки без K.', 'type' => 'number', 'min' => 0.0, 'max' => 1.0, 'step' => 0.01],
                    ['path' => 'quality_score_with_k', 'label' => 'Quality with K', 'description' => 'Score для калибровки с ΔEC/K.', 'type' => 'number', 'min' => 0.0, 'max' => 1.0, 'step' => 0.01],
                    ['path' => 'quality_score_legacy', 'label' => 'Quality legacy', 'description' => 'Score для legacy backfill.', 'type' => 'number', 'min' => 0.0, 'max' => 1.0, 'step' => 0.01],
                    ['path' => 'age_warning_days', 'label' => 'Age warning days', 'description' => 'Порог предупреждения по возрасту калибровки.', 'type' => 'integer', 'min' => 1, 'max' => 365],
                    ['path' => 'age_critical_days', 'label' => 'Age critical days', 'description' => 'Критичный возраст калибровки.', 'type' => 'integer', 'min' => 7, 'max' => 365],
                    ['path' => 'default_run_duration_sec', 'label' => 'Default run sec', 'description' => 'Длительность по умолчанию для UI.', 'type' => 'integer', 'min' => 5, 'max' => 60],
                ],
            ],
        ],
        'sensor_calibration' => [
            [
                'key' => 'sensor_calibration',
                'label' => 'Калибровка сенсоров',
                'description' => 'Системные значения мастера pH/EC calibration.',
                'fields' => [
                    ['path' => 'ph_point_1_value', 'label' => 'pH point 1', 'description' => 'Рекомендуемый буфер для первой точки pH.', 'type' => 'number', 'min' => 1.0, 'max' => 14.0, 'step' => 0.01],
                    ['path' => 'ph_point_2_value', 'label' => 'pH point 2', 'description' => 'Рекомендуемый буфер для второй точки pH.', 'type' => 'number', 'min' => 1.0, 'max' => 14.0, 'step' => 0.01],
                    ['path' => 'ec_point_1_tds', 'label' => 'EC point 1 ppm', 'description' => 'Рекомендуемый TDS для первой точки EC.', 'type' => 'integer', 'min' => 100, 'max' => 10000],
                    ['path' => 'ec_point_2_tds', 'label' => 'EC point 2 ppm', 'description' => 'Рекомендуемый TDS для второй точки EC.', 'type' => 'integer', 'min' => 50, 'max' => 10000],
                    ['path' => 'reminder_days', 'label' => 'Reminder days', 'description' => 'Через сколько дней показывать warning.', 'type' => 'integer', 'min' => 7, 'max' => 365],
                    ['path' => 'critical_days', 'label' => 'Critical days', 'description' => 'Через сколько дней показывать critical.', 'type' => 'integer', 'min' => 14, 'max' => 365],
                    ['path' => 'command_timeout_sec', 'label' => 'Command timeout sec', 'description' => 'Таймаут команды calibrate.', 'type' => 'integer', 'min' => 5, 'max' => 60],
                    ['path' => 'ph_reference_min', 'label' => 'Min pH reference', 'description' => 'Минимально допустимое значение pH reference.', 'type' => 'number', 'min' => 0.0, 'max' => 6.0, 'step' => 0.01],
                    ['path' => 'ph_reference_max', 'label' => 'Max pH reference', 'description' => 'Максимально допустимое значение pH reference.', 'type' => 'number', 'min' => 8.0, 'max' => 14.0, 'step' => 0.01],
                    ['path' => 'ec_tds_reference_max', 'label' => 'Max EC TDS ref', 'description' => 'Максимальный допустимый reference для EC.', 'type' => 'integer', 'min' => 1000, 'max' => 20000],
                ],
            ],
        ],
        'automation_defaults' => [
            [
                'key' => 'automation_profile_climate',
                'label' => 'Automation profile: climate',
                'description' => 'Рекомендуемые значения климатического профиля в UI автоматики.',
                'fields' => [
                    ['path' => 'climate_enabled', 'label' => 'Climate enabled', 'description' => 'Включать climate subsystem по умолчанию.', 'type' => 'boolean'],
                    ['path' => 'climate_day_temp_c', 'label' => 'Climate day temp', 'description' => 'Дневная температура.', 'type' => 'number', 'min' => 10.0, 'max' => 35.0, 'step' => 0.1],
                    ['path' => 'climate_night_temp_c', 'label' => 'Climate night temp', 'description' => 'Ночная температура.', 'type' => 'number', 'min' => 10.0, 'max' => 35.0, 'step' => 0.1],
                    ['path' => 'climate_day_humidity_pct', 'label' => 'Climate day humidity', 'description' => 'Дневная влажность.', 'type' => 'number', 'min' => 30.0, 'max' => 90.0, 'step' => 0.1],
                    ['path' => 'climate_night_humidity_pct', 'label' => 'Climate night humidity', 'description' => 'Ночная влажность.', 'type' => 'number', 'min' => 30.0, 'max' => 90.0, 'step' => 0.1],
                    ['path' => 'climate_interval_min', 'label' => 'Climate interval min', 'description' => 'Период климатического шага.', 'type' => 'integer', 'min' => 1, 'max' => 1440],
                    ['path' => 'climate_day_start_hhmm', 'label' => 'Climate day start', 'description' => 'Начало дневного режима.', 'type' => 'string'],
                    ['path' => 'climate_night_start_hhmm', 'label' => 'Climate night start', 'description' => 'Начало ночного режима.', 'type' => 'string'],
                    ['path' => 'climate_vent_min_pct', 'label' => 'Climate vent min', 'description' => 'Минимальное открытие форточек.', 'type' => 'integer', 'min' => 0, 'max' => 100],
                    ['path' => 'climate_vent_max_pct', 'label' => 'Climate vent max', 'description' => 'Максимальное открытие форточек.', 'type' => 'integer', 'min' => 0, 'max' => 100],
                    ['path' => 'climate_use_external_telemetry', 'label' => 'Climate external telemetry', 'description' => 'Использовать external guard.', 'type' => 'boolean'],
                    ['path' => 'climate_outside_temp_min_c', 'label' => 'Climate outside temp min', 'description' => 'Нижний порог outside temperature.', 'type' => 'number', 'min' => -30.0, 'max' => 45.0, 'step' => 0.1],
                    ['path' => 'climate_outside_temp_max_c', 'label' => 'Climate outside temp max', 'description' => 'Верхний порог outside temperature.', 'type' => 'number', 'min' => -30.0, 'max' => 45.0, 'step' => 0.1],
                    ['path' => 'climate_outside_humidity_max_pct', 'label' => 'Climate outside humidity max', 'description' => 'Максимальная внешняя влажность.', 'type' => 'integer', 'min' => 20, 'max' => 100],
                    ['path' => 'climate_manual_override_enabled', 'label' => 'Climate manual override', 'description' => 'Разрешать manual override.', 'type' => 'boolean'],
                    ['path' => 'climate_manual_override_minutes', 'label' => 'Climate override minutes', 'description' => 'Длительность manual override.', 'type' => 'integer', 'min' => 5, 'max' => 120],
                ],
            ],
            [
                'key' => 'automation_profile_water',
                'label' => 'Automation profile: water',
                'description' => 'Рекомендуемые значения водного узла и automation runtime defaults.',
                'fields' => [
                    ['path' => 'water_system_type', 'label' => 'Water system type', 'description' => 'Тип irrigation system по умолчанию.', 'type' => 'string'],
                    ['path' => 'water_tanks_count', 'label' => 'Water tanks count', 'description' => 'Количество баков по умолчанию.', 'type' => 'integer', 'min' => 2, 'max' => 3],
                    ['path' => 'water_clean_tank_fill_l', 'label' => 'Clean tank fill L', 'description' => 'Объём чистого бака.', 'type' => 'integer', 'min' => 10, 'max' => 5000],
                    ['path' => 'water_nutrient_tank_target_l', 'label' => 'Nutrient tank target L', 'description' => 'Целевой объём бака раствора.', 'type' => 'integer', 'min' => 10, 'max' => 5000],
                    ['path' => 'water_irrigation_batch_l', 'label' => 'Irrigation batch L', 'description' => 'Объём одной порции полива.', 'type' => 'integer', 'min' => 1, 'max' => 500],
                    ['path' => 'water_interval_min', 'label' => 'Water interval min', 'description' => 'Интервал между поливами.', 'type' => 'integer', 'min' => 1, 'max' => 1440],
                    ['path' => 'water_duration_sec', 'label' => 'Water duration sec', 'description' => 'Длительность одного полива.', 'type' => 'integer', 'min' => 1, 'max' => 3600],
                    ['path' => 'water_fill_temperature_c', 'label' => 'Water fill temp', 'description' => 'Целевая температура воды.', 'type' => 'number', 'min' => 5.0, 'max' => 35.0, 'step' => 0.1],
                    ['path' => 'water_fill_window_start_hhmm', 'label' => 'Fill window start', 'description' => 'Начало окна набора.', 'type' => 'string'],
                    ['path' => 'water_fill_window_end_hhmm', 'label' => 'Fill window end', 'description' => 'Конец окна набора.', 'type' => 'string'],
                    ['path' => 'water_target_ph', 'label' => 'Target pH', 'description' => 'Целевой pH.', 'type' => 'number', 'min' => 4.0, 'max' => 9.0, 'step' => 0.01],
                    ['path' => 'water_target_ec', 'label' => 'Target EC', 'description' => 'Целевой EC.', 'type' => 'number', 'min' => 0.1, 'max' => 10.0, 'step' => 0.01],
                    ['path' => 'water_ph_pct', 'label' => 'pH pct', 'description' => 'Процент допуска по pH.', 'type' => 'number', 'min' => 1.0, 'max' => 50.0, 'step' => 0.1],
                    ['path' => 'water_ec_pct', 'label' => 'EC pct', 'description' => 'Процент допуска по EC.', 'type' => 'number', 'min' => 1.0, 'max' => 50.0, 'step' => 0.1],
                    ['path' => 'water_valve_switching_enabled', 'label' => 'Valve switching', 'description' => 'Разрешать переключение клапанов.', 'type' => 'boolean'],
                    ['path' => 'water_correction_during_irrigation', 'label' => 'Correction during irrigation', 'description' => 'Разрешать коррекцию во время полива.', 'type' => 'boolean'],
                    ['path' => 'water_drain_control_enabled', 'label' => 'Drain control enabled', 'description' => 'Включать drain control по умолчанию.', 'type' => 'boolean'],
                    ['path' => 'water_drain_target_pct', 'label' => 'Drain target pct', 'description' => 'Целевой дренаж.', 'type' => 'integer', 'min' => 0, 'max' => 100],
                    ['path' => 'water_diagnostics_enabled', 'label' => 'Diagnostics enabled', 'description' => 'Включать diagnostics subsystem.', 'type' => 'boolean'],
                    ['path' => 'water_diagnostics_interval_min', 'label' => 'Diagnostics interval', 'description' => 'Период diagnostics workflow.', 'type' => 'integer', 'min' => 1, 'max' => 1440],
                    ['path' => 'water_cycle_start_workflow_enabled', 'label' => 'Cycle-start workflow', 'description' => 'Включать startup/cycle_start workflow.', 'type' => 'boolean'],
                    ['path' => 'water_diagnostics_workflow', 'label' => 'Diagnostics workflow', 'description' => 'Workflow по умолчанию: startup, cycle_start или diagnostics.', 'type' => 'string'],
                    ['path' => 'water_clean_tank_full_threshold', 'label' => 'Clean tank full threshold', 'description' => 'Порог полного clean tank.', 'type' => 'number', 'min' => 0.05, 'max' => 1.0, 'step' => 0.01],
                    ['path' => 'water_refill_duration_sec', 'label' => 'Refill duration', 'description' => 'Длительность refill.', 'type' => 'integer', 'min' => 1, 'max' => 3600],
                    ['path' => 'water_refill_timeout_sec', 'label' => 'Refill timeout', 'description' => 'Таймаут refill.', 'type' => 'integer', 'min' => 30, 'max' => 86400],
                    ['path' => 'water_startup_clean_fill_timeout_sec', 'label' => 'Startup clean fill timeout', 'description' => 'Таймаут clean_fill в startup.', 'type' => 'integer', 'min' => 30, 'max' => 86400],
                    ['path' => 'water_startup_solution_fill_timeout_sec', 'label' => 'Startup solution fill timeout', 'description' => 'Таймаут solution_fill в startup.', 'type' => 'integer', 'min' => 30, 'max' => 86400],
                    ['path' => 'water_startup_prepare_recirculation_timeout_sec', 'label' => 'Startup prepare recirculation timeout', 'description' => 'Таймаут prepare_recirculation.', 'type' => 'integer', 'min' => 30, 'max' => 86400],
                    ['path' => 'water_startup_clean_fill_retry_cycles', 'label' => 'Startup clean fill retries', 'description' => 'Повторы clean_fill.', 'type' => 'integer', 'min' => 0, 'max' => 20],
                    ['path' => 'water_startup_level_poll_interval_sec', 'label' => 'Startup level poll', 'description' => 'Интервал level polling в startup.', 'type' => 'integer', 'min' => 5, 'max' => 3600],
                    ['path' => 'water_startup_level_switch_on_threshold', 'label' => 'Startup level threshold', 'description' => 'Порог level switch.', 'type' => 'number', 'min' => 0.0, 'max' => 1.0, 'step' => 0.01],
                    ['path' => 'water_startup_clean_max_sensor_label', 'label' => 'Clean max sensor label', 'description' => 'Label верхнего датчика clean tank.', 'type' => 'string'],
                    ['path' => 'water_startup_solution_max_sensor_label', 'label' => 'Solution max sensor label', 'description' => 'Label верхнего датчика solution tank.', 'type' => 'string'],
                    ['path' => 'water_irrigation_recovery_max_continue_attempts', 'label' => 'Irrigation recovery max continue', 'description' => 'Максимум попыток продолжить цикл после recovery.', 'type' => 'integer', 'min' => 1, 'max' => 30],
                    ['path' => 'water_irrigation_recovery_timeout_sec', 'label' => 'Irrigation recovery timeout', 'description' => 'Таймаут recovery.', 'type' => 'integer', 'min' => 30, 'max' => 86400],
                    ['path' => 'water_irrigation_recovery_target_tolerance_ec_pct', 'label' => 'Recovery target tol EC', 'description' => 'Target tolerance EC для recovery.', 'type' => 'number', 'min' => 0.1, 'max' => 100.0, 'step' => 0.1],
                    ['path' => 'water_irrigation_recovery_target_tolerance_ph_pct', 'label' => 'Recovery target tol pH', 'description' => 'Target tolerance pH для recovery.', 'type' => 'number', 'min' => 0.1, 'max' => 100.0, 'step' => 0.1],
                    ['path' => 'water_irrigation_recovery_degraded_tolerance_ec_pct', 'label' => 'Recovery degraded tol EC', 'description' => 'Degraded tolerance EC для recovery.', 'type' => 'number', 'min' => 0.1, 'max' => 100.0, 'step' => 0.1],
                    ['path' => 'water_irrigation_recovery_degraded_tolerance_ph_pct', 'label' => 'Recovery degraded tol pH', 'description' => 'Degraded tolerance pH для recovery.', 'type' => 'number', 'min' => 0.1, 'max' => 100.0, 'step' => 0.1],
                    ['path' => 'water_prepare_tolerance_ec_pct', 'label' => 'Prepare tolerance EC', 'description' => 'EC tolerance в prepare.', 'type' => 'number', 'min' => 0.1, 'max' => 100.0, 'step' => 0.1],
                    ['path' => 'water_prepare_tolerance_ph_pct', 'label' => 'Prepare tolerance pH', 'description' => 'pH tolerance в prepare.', 'type' => 'number', 'min' => 0.1, 'max' => 100.0, 'step' => 0.1],
                    ['path' => 'water_correction_max_ec_attempts', 'label' => 'Correction max EC attempts', 'description' => 'Максимум EC correction attempts.', 'type' => 'integer', 'min' => 1, 'max' => 500],
                    ['path' => 'water_correction_max_ph_attempts', 'label' => 'Correction max pH attempts', 'description' => 'Максимум pH correction attempts.', 'type' => 'integer', 'min' => 1, 'max' => 500],
                    ['path' => 'water_correction_prepare_recirculation_max_attempts', 'label' => 'Correction prepare recirculation max attempts', 'description' => 'Количество окон recirculation.', 'type' => 'integer', 'min' => 1, 'max' => 50],
                    ['path' => 'water_correction_prepare_recirculation_max_correction_attempts', 'label' => 'Correction prepare recirc cap', 'description' => 'Guard correction loop внутри одного окна.', 'type' => 'integer', 'min' => 1, 'max' => 500],
                    ['path' => 'water_correction_stabilization_sec', 'label' => 'Correction stabilization', 'description' => 'Ожидание перед corr_check.', 'type' => 'integer', 'min' => 0, 'max' => 3600],
                    ['path' => 'water_two_tank_clean_fill_start_steps', 'label' => 'Clean fill start steps', 'description' => 'Количество relay steps для clean_fill_start.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_clean_fill_stop_steps', 'label' => 'Clean fill stop steps', 'description' => 'Количество relay steps для clean_fill_stop.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_solution_fill_start_steps', 'label' => 'Solution fill start steps', 'description' => 'Количество relay steps для solution_fill_start.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_solution_fill_stop_steps', 'label' => 'Solution fill stop steps', 'description' => 'Количество relay steps для solution_fill_stop.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_prepare_recirculation_start_steps', 'label' => 'Prepare recirculation start steps', 'description' => 'Количество relay steps для prepare_recirculation_start.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_prepare_recirculation_stop_steps', 'label' => 'Prepare recirculation stop steps', 'description' => 'Количество relay steps для prepare_recirculation_stop.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_irrigation_recovery_start_steps', 'label' => 'Irrigation recovery start steps', 'description' => 'Количество relay steps для irrigation_recovery_start.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_irrigation_recovery_stop_steps', 'label' => 'Irrigation recovery stop steps', 'description' => 'Количество relay steps для irrigation_recovery_stop.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_refill_required_node_types_csv', 'label' => 'Refill required node types', 'description' => 'CSV список required node types.', 'type' => 'string'],
                    ['path' => 'water_refill_preferred_channel', 'label' => 'Refill preferred channel', 'description' => 'Предпочтительный channel для refill.', 'type' => 'string'],
                    ['path' => 'water_solution_change_enabled', 'label' => 'Solution change enabled', 'description' => 'Включать solution_change по умолчанию.', 'type' => 'boolean'],
                    ['path' => 'water_solution_change_interval_min', 'label' => 'Solution change interval', 'description' => 'Интервал solution_change.', 'type' => 'integer', 'min' => 1, 'max' => 1440],
                    ['path' => 'water_solution_change_duration_sec', 'label' => 'Solution change duration', 'description' => 'Длительность solution_change.', 'type' => 'integer', 'min' => 1, 'max' => 86400],
                    ['path' => 'water_manual_irrigation_sec', 'label' => 'Manual irrigation sec', 'description' => 'Длительность ручного полива.', 'type' => 'integer', 'min' => 1, 'max' => 3600],
                ],
            ],
            [
                'key' => 'automation_profile_lighting',
                'label' => 'Automation profile: lighting',
                'description' => 'Рекомендуемые значения lighting profile в UI автоматики.',
                'fields' => [
                    ['path' => 'lighting_enabled', 'label' => 'Lighting enabled', 'description' => 'Включать lighting subsystem по умолчанию.', 'type' => 'boolean'],
                    ['path' => 'lighting_lux_day', 'label' => 'Lighting lux day', 'description' => 'Дневной lux.', 'type' => 'integer', 'min' => 0, 'max' => 120000],
                    ['path' => 'lighting_lux_night', 'label' => 'Lighting lux night', 'description' => 'Ночной lux.', 'type' => 'integer', 'min' => 0, 'max' => 120000],
                    ['path' => 'lighting_hours_on', 'label' => 'Lighting hours on', 'description' => 'Длительность досветки.', 'type' => 'number', 'min' => 0.0, 'max' => 24.0, 'step' => 0.1],
                    ['path' => 'lighting_interval_min', 'label' => 'Lighting interval', 'description' => 'Период lighting control.', 'type' => 'integer', 'min' => 1, 'max' => 1440],
                    ['path' => 'lighting_schedule_start_hhmm', 'label' => 'Lighting start', 'description' => 'Начало фотопериода.', 'type' => 'string'],
                    ['path' => 'lighting_schedule_end_hhmm', 'label' => 'Lighting end', 'description' => 'Конец фотопериода.', 'type' => 'string'],
                    ['path' => 'lighting_manual_intensity_pct', 'label' => 'Lighting manual intensity', 'description' => 'Интенсивность manual override.', 'type' => 'integer', 'min' => 0, 'max' => 100],
                    ['path' => 'lighting_manual_duration_hours', 'label' => 'Lighting manual duration', 'description' => 'Длительность manual override.', 'type' => 'number', 'min' => 0.5, 'max' => 24.0, 'step' => 0.5],
                ],
            ],
        ],
        'automation_command_templates' => [
            [
                'key' => 'automation_command_templates',
                'label' => 'Automation command templates',
                'description' => 'Шаблоны relay-команд two-tank automation runtime.',
                'fields' => [
                    ['path' => 'clean_fill_start', 'label' => 'clean_fill_start', 'description' => 'Команды запуска clean_fill.', 'type' => 'json'],
                    ['path' => 'clean_fill_stop', 'label' => 'clean_fill_stop', 'description' => 'Команды остановки clean_fill.', 'type' => 'json'],
                    ['path' => 'solution_fill_start', 'label' => 'solution_fill_start', 'description' => 'Команды запуска solution_fill.', 'type' => 'json'],
                    ['path' => 'solution_fill_stop', 'label' => 'solution_fill_stop', 'description' => 'Команды остановки solution_fill.', 'type' => 'json'],
                    ['path' => 'prepare_recirculation_start', 'label' => 'prepare_recirculation_start', 'description' => 'Команды запуска prepare_recirculation.', 'type' => 'json'],
                    ['path' => 'prepare_recirculation_stop', 'label' => 'prepare_recirculation_stop', 'description' => 'Команды остановки prepare_recirculation.', 'type' => 'json'],
                    ['path' => 'irrigation_recovery_start', 'label' => 'irrigation_recovery_start', 'description' => 'Команды запуска irrigation_recovery.', 'type' => 'json'],
                    ['path' => 'irrigation_recovery_stop', 'label' => 'irrigation_recovery_stop', 'description' => 'Команды остановки irrigation_recovery.', 'type' => 'json'],
                ],
            ],
        ],
    ];

    public static function allDefaults(): array
    {
        return [
            'pump_calibration' => [
                'ml_per_sec_min' => 0.01,
                'ml_per_sec_max' => 20.0,
                'min_dose_ms' => 50,
                'calibration_duration_min_sec' => 1,
                'calibration_duration_max_sec' => 120,
                'quality_score_basic' => 0.75,
                'quality_score_with_k' => 0.90,
                'quality_score_legacy' => 0.50,
                'age_warning_days' => 30,
                'age_critical_days' => 90,
                'default_run_duration_sec' => 20,
            ],
            'sensor_calibration' => [
                'ph_point_1_value' => 7.0,
                'ph_point_2_value' => 4.01,
                'ec_point_1_tds' => 1413,
                'ec_point_2_tds' => 707,
                'reminder_days' => 30,
                'critical_days' => 90,
                'command_timeout_sec' => 10,
                'ph_reference_min' => 1.0,
                'ph_reference_max' => 12.0,
                'ec_tds_reference_max' => 10000,
            ],
            'pid_defaults_ph' => [
                'target' => 5.8,
                'dead_zone' => 0.05,
                'close_zone' => 0.3,
                'far_zone' => 1.0,
                'zone_coeffs' => [
                    'close' => [
                        'kp' => 5.0,
                        'ki' => 0.05,
                        'kd' => 0.0,
                    ],
                    'far' => [
                        'kp' => 8.0,
                        'ki' => 0.02,
                        'kd' => 0.0,
                    ],
                ],
                'max_output' => 20.0,
                'min_interval_ms' => 90000,
                'max_integral' => 20.0,
            ],
            'pid_defaults_ec' => [
                'target' => 1.6,
                'dead_zone' => 0.1,
                'close_zone' => 0.5,
                'far_zone' => 1.5,
                'zone_coeffs' => [
                    'close' => [
                        'kp' => 30.0,
                        'ki' => 0.3,
                        'kd' => 0.0,
                    ],
                    'far' => [
                        'kp' => 50.0,
                        'ki' => 0.1,
                        'kd' => 0.0,
                    ],
                ],
                'max_output' => 50.0,
                'min_interval_ms' => 120000,
                'max_integral' => 100.0,
            ],
            'automation_defaults' => [
                'climate_enabled' => true,
                'climate_day_temp_c' => 23.0,
                'climate_night_temp_c' => 20.0,
                'climate_day_humidity_pct' => 62.0,
                'climate_night_humidity_pct' => 70.0,
                'climate_interval_min' => 5,
                'climate_day_start_hhmm' => '07:00',
                'climate_night_start_hhmm' => '19:00',
                'climate_vent_min_pct' => 15,
                'climate_vent_max_pct' => 85,
                'climate_use_external_telemetry' => true,
                'climate_outside_temp_min_c' => 4.0,
                'climate_outside_temp_max_c' => 34.0,
                'climate_outside_humidity_max_pct' => 90,
                'climate_manual_override_enabled' => true,
                'climate_manual_override_minutes' => 30,
                'water_system_type' => 'drip',
                'water_tanks_count' => 2,
                'water_clean_tank_fill_l' => 300,
                'water_nutrient_tank_target_l' => 280,
                'water_irrigation_batch_l' => 20,
                'water_interval_min' => 30,
                'water_duration_sec' => 120,
                'water_fill_temperature_c' => 20.0,
                'water_fill_window_start_hhmm' => '05:00',
                'water_fill_window_end_hhmm' => '07:00',
                'water_target_ph' => 5.8,
                'water_target_ec' => 1.6,
                'water_ph_pct' => 5.0,
                'water_ec_pct' => 10.0,
                'water_valve_switching_enabled' => true,
                'water_correction_during_irrigation' => true,
                'water_drain_control_enabled' => false,
                'water_drain_target_pct' => 20,
                'water_diagnostics_enabled' => true,
                'water_diagnostics_interval_min' => 15,
                'water_cycle_start_workflow_enabled' => true,
                'water_diagnostics_workflow' => 'startup',
                'water_clean_tank_full_threshold' => 0.95,
                'water_refill_duration_sec' => 30,
                'water_refill_timeout_sec' => 600,
                'water_startup_clean_fill_timeout_sec' => 1200,
                'water_startup_solution_fill_timeout_sec' => 1800,
                'water_startup_prepare_recirculation_timeout_sec' => 1200,
                'water_startup_clean_fill_retry_cycles' => 1,
                'water_startup_level_poll_interval_sec' => 60,
                'water_startup_level_switch_on_threshold' => 0.5,
                'water_startup_clean_max_sensor_label' => 'level_clean_max',
                'water_startup_solution_max_sensor_label' => 'level_solution_max',
                'water_irrigation_recovery_max_continue_attempts' => 5,
                'water_irrigation_recovery_timeout_sec' => 600,
                'water_irrigation_recovery_target_tolerance_ec_pct' => 10.0,
                'water_irrigation_recovery_target_tolerance_ph_pct' => 5.0,
                'water_irrigation_recovery_degraded_tolerance_ec_pct' => 20.0,
                'water_irrigation_recovery_degraded_tolerance_ph_pct' => 10.0,
                'water_prepare_tolerance_ec_pct' => 25.0,
                'water_prepare_tolerance_ph_pct' => 15.0,
                'water_correction_max_ec_attempts' => 5,
                'water_correction_max_ph_attempts' => 5,
                'water_correction_prepare_recirculation_max_attempts' => 3,
                'water_correction_prepare_recirculation_max_correction_attempts' => 20,
                'water_correction_stabilization_sec' => 60,
                'water_two_tank_clean_fill_start_steps' => 1,
                'water_two_tank_clean_fill_stop_steps' => 1,
                'water_two_tank_solution_fill_start_steps' => 3,
                'water_two_tank_solution_fill_stop_steps' => 3,
                'water_two_tank_prepare_recirculation_start_steps' => 3,
                'water_two_tank_prepare_recirculation_stop_steps' => 3,
                'water_two_tank_irrigation_recovery_start_steps' => 4,
                'water_two_tank_irrigation_recovery_stop_steps' => 3,
                'water_refill_required_node_types_csv' => 'irrig',
                'water_refill_preferred_channel' => 'fill_valve',
                'water_solution_change_enabled' => false,
                'water_solution_change_interval_min' => 180,
                'water_solution_change_duration_sec' => 120,
                'water_manual_irrigation_sec' => 90,
                'lighting_enabled' => true,
                'lighting_lux_day' => 18000,
                'lighting_lux_night' => 0,
                'lighting_hours_on' => 16.0,
                'lighting_interval_min' => 30,
                'lighting_schedule_start_hhmm' => '06:00',
                'lighting_schedule_end_hhmm' => '22:00',
                'lighting_manual_intensity_pct' => 75,
                'lighting_manual_duration_hours' => 4.0,
            ],
            'automation_command_templates' => [
                'clean_fill_start' => [
                    ['channel' => 'valve_clean_fill', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                ],
                'clean_fill_stop' => [
                    ['channel' => 'valve_clean_fill', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                ],
                'solution_fill_start' => [
                    ['channel' => 'valve_clean_supply', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'valve_solution_fill', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                ],
                'solution_fill_stop' => [
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_solution_fill', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_clean_supply', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                ],
                'prepare_recirculation_start' => [
                    ['channel' => 'valve_solution_supply', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'valve_solution_fill', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                ],
                'prepare_recirculation_stop' => [
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_solution_fill', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_solution_supply', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                ],
                'irrigation_recovery_start' => [
                    ['channel' => 'valve_irrigation', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_solution_supply', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'valve_solution_fill', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                ],
                'irrigation_recovery_stop' => [
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_solution_fill', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_solution_supply', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                ],
            ],
        ];
    }

    public static function namespaces(): array
    {
        return array_keys(self::FIELD_CATALOG);
    }

    public static function defaults(string $namespace): array
    {
        $defaults = self::allDefaults();
        if (! array_key_exists($namespace, $defaults)) {
            throw new InvalidArgumentException("Unknown automation settings namespace: {$namespace}");
        }

        return $defaults[$namespace];
    }

    public static function fieldCatalog(string $namespace): array
    {
        if (! array_key_exists($namespace, self::FIELD_CATALOG)) {
            throw new InvalidArgumentException("Unknown automation settings namespace: {$namespace}");
        }

        return self::FIELD_CATALOG[$namespace];
    }

    public static function flattenFields(string $namespace): array
    {
        $fields = [];
        foreach (self::fieldCatalog($namespace) as $section) {
            foreach ($section['fields'] as $field) {
                $fields[$field['path']] = $field;
            }
        }

        return $fields;
    }

    public static function validate(string $namespace, array $config, bool $allowPartial = true): array
    {
        if ($config === []) {
            return [];
        }
        if (array_is_list($config)) {
            throw new InvalidArgumentException("Namespace {$namespace} must be an object.");
        }

        $defaults = self::defaults($namespace);
        $fields = self::flattenFields($namespace);

        foreach ($config as $key => $value) {
            if (! array_key_exists($key, $fields)) {
                throw new InvalidArgumentException("Unknown field {$namespace}.{$key}");
            }
            self::validateField($fields[$key], $value);
        }

        if (! $allowPartial) {
            foreach (array_keys($defaults) as $requiredKey) {
                if (! array_key_exists($requiredKey, $config)) {
                    throw new InvalidArgumentException("Field {$namespace}.{$requiredKey} is required.");
                }
            }
        }

        self::validateConsistency($namespace, $config, $allowPartial);

        return $config;
    }

    public static function merge(array $base, array $override): array
    {
        return ZoneCorrectionConfigCatalog::merge($base, $override);
    }

    public static function diff(array $base, array $target): array
    {
        return ZoneCorrectionConfigCatalog::diff($base, $target);
    }

    private static function validateField(array $field, mixed $value): void
    {
        $path = (string) $field['path'];
        $type = (string) $field['type'];

        if ($type === 'integer') {
            if (! is_int($value)) {
                throw new InvalidArgumentException("Field {$path} must be integer.");
            }
        } elseif ($type === 'number') {
            if (! is_numeric($value)) {
                throw new InvalidArgumentException("Field {$path} must be numeric.");
            }
            $value = (float) $value;
        } elseif ($type === 'boolean') {
            if (! is_bool($value)) {
                throw new InvalidArgumentException("Field {$path} must be boolean.");
            }
        } elseif ($type === 'json') {
            if (! is_array($value)) {
                throw new InvalidArgumentException("Field {$path} must be JSON array/object.");
            }
        } elseif (! is_string($value)) {
            throw new InvalidArgumentException("Field {$path} must be string.");
        }

        if (isset($field['min']) && $value < $field['min']) {
            throw new InvalidArgumentException("Field {$path} must be >= {$field['min']}.");
        }
        if (isset($field['max']) && $value > $field['max']) {
            throw new InvalidArgumentException("Field {$path} must be <= {$field['max']}.");
        }
    }

    private static function validateConsistency(string $namespace, array $config, bool $allowPartial): void
    {
        $effectiveConfig = $allowPartial
            ? self::merge(self::defaults($namespace), $config)
            : $config;

        if ($namespace === 'pump_calibration') {
            $mlPerSecMin = (float) ($effectiveConfig['ml_per_sec_min'] ?? 0);
            $mlPerSecMax = (float) ($effectiveConfig['ml_per_sec_max'] ?? 0);
            $calibrationDurationMin = (int) ($effectiveConfig['calibration_duration_min_sec'] ?? 0);
            $calibrationDurationMax = (int) ($effectiveConfig['calibration_duration_max_sec'] ?? 0);
            $ageWarningDays = (int) ($effectiveConfig['age_warning_days'] ?? 0);
            $ageCriticalDays = (int) ($effectiveConfig['age_critical_days'] ?? 0);

            if ($mlPerSecMin > $mlPerSecMax) {
                throw new InvalidArgumentException('Field pump_calibration.ml_per_sec_min must be <= pump_calibration.ml_per_sec_max.');
            }
            if ($calibrationDurationMin > $calibrationDurationMax) {
                throw new InvalidArgumentException('Field pump_calibration.calibration_duration_min_sec must be <= pump_calibration.calibration_duration_max_sec.');
            }
            if ($ageWarningDays > $ageCriticalDays) {
                throw new InvalidArgumentException('Field pump_calibration.age_warning_days must be <= pump_calibration.age_critical_days.');
            }

            return;
        }

        if ($namespace === 'sensor_calibration') {
            $phReferenceMin = (float) ($effectiveConfig['ph_reference_min'] ?? 0);
            $phReferenceMax = (float) ($effectiveConfig['ph_reference_max'] ?? 0);
            $reminderDays = (int) ($effectiveConfig['reminder_days'] ?? 0);
            $criticalDays = (int) ($effectiveConfig['critical_days'] ?? 0);

            if ($phReferenceMin > $phReferenceMax) {
                throw new InvalidArgumentException('Field sensor_calibration.ph_reference_min must be <= sensor_calibration.ph_reference_max.');
            }
            if ($reminderDays > $criticalDays) {
                throw new InvalidArgumentException('Field sensor_calibration.reminder_days must be <= sensor_calibration.critical_days.');
            }

            return;
        }

        if ($namespace === 'automation_defaults') {
            $ventMin = (int) ($effectiveConfig['climate_vent_min_pct'] ?? 0);
            $ventMax = (int) ($effectiveConfig['climate_vent_max_pct'] ?? 0);
            $outsideTempMin = (float) ($effectiveConfig['climate_outside_temp_min_c'] ?? 0);
            $outsideTempMax = (float) ($effectiveConfig['climate_outside_temp_max_c'] ?? 0);
            $tanksCount = (int) ($effectiveConfig['water_tanks_count'] ?? 0);
            $systemType = (string) ($effectiveConfig['water_system_type'] ?? '');
            $workflow = (string) ($effectiveConfig['water_diagnostics_workflow'] ?? '');
            $targetEcTolerance = (float) ($effectiveConfig['water_irrigation_recovery_target_tolerance_ec_pct'] ?? 0);
            $targetPhTolerance = (float) ($effectiveConfig['water_irrigation_recovery_target_tolerance_ph_pct'] ?? 0);
            $degradedEcTolerance = (float) ($effectiveConfig['water_irrigation_recovery_degraded_tolerance_ec_pct'] ?? 0);
            $degradedPhTolerance = (float) ($effectiveConfig['water_irrigation_recovery_degraded_tolerance_ph_pct'] ?? 0);

            if ($ventMin > $ventMax) {
                throw new InvalidArgumentException('Field automation_defaults.climate_vent_min_pct must be <= automation_defaults.climate_vent_max_pct.');
            }
            if ($outsideTempMin > $outsideTempMax) {
                throw new InvalidArgumentException('Field automation_defaults.climate_outside_temp_min_c must be <= automation_defaults.climate_outside_temp_max_c.');
            }
            if (! in_array($systemType, ['drip', 'substrate_trays', 'nft'], true)) {
                throw new InvalidArgumentException('Field automation_defaults.water_system_type must be one of: drip, substrate_trays, nft.');
            }
            if (! in_array($tanksCount, [2, 3], true)) {
                throw new InvalidArgumentException('Field automation_defaults.water_tanks_count must be 2 or 3.');
            }
            if (! in_array($workflow, ['startup', 'cycle_start', 'diagnostics'], true)) {
                throw new InvalidArgumentException('Field automation_defaults.water_diagnostics_workflow must be one of: startup, cycle_start, diagnostics.');
            }
            if ($targetEcTolerance > $degradedEcTolerance) {
                throw new InvalidArgumentException('Field automation_defaults.water_irrigation_recovery_target_tolerance_ec_pct must be <= automation_defaults.water_irrigation_recovery_degraded_tolerance_ec_pct.');
            }
            if ($targetPhTolerance > $degradedPhTolerance) {
                throw new InvalidArgumentException('Field automation_defaults.water_irrigation_recovery_target_tolerance_ph_pct must be <= automation_defaults.water_irrigation_recovery_degraded_tolerance_ph_pct.');
            }

            return;
        }

        if ($namespace === 'automation_command_templates') {
            foreach ($effectiveConfig as $path => $commands) {
                self::assertRelayCommandTemplate((string) $path, $commands);
            }
        }
    }

    private static function assertRelayCommandTemplate(string $path, mixed $commands): void
    {
        if (! is_array($commands) || ! array_is_list($commands)) {
            throw new InvalidArgumentException("Field automation_command_templates.{$path} must be a JSON array of commands.");
        }

        foreach ($commands as $index => $command) {
            if (! is_array($command) || array_is_list($command)) {
                throw new InvalidArgumentException("Field automation_command_templates.{$path}[{$index}] must be an object.");
            }

            $channel = $command['channel'] ?? null;
            $cmd = $command['cmd'] ?? null;
            $params = is_array($command['params'] ?? null) ? $command['params'] : null;

            if (! is_string($channel) || trim($channel) === '') {
                throw new InvalidArgumentException("Field automation_command_templates.{$path}[{$index}].channel must be non-empty string.");
            }
            if ($cmd !== 'set_relay') {
                throw new InvalidArgumentException("Field automation_command_templates.{$path}[{$index}].cmd must be set_relay.");
            }
            if (! is_bool($params['state'] ?? null)) {
                throw new InvalidArgumentException("Field automation_command_templates.{$path}[{$index}].params.state must be boolean.");
            }
        }
    }
}
