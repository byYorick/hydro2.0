<?php

namespace App\Services;

use App\Support\Automation\FieldCatalogHelpBuilder;
use App\Support\Automation\ObservabilityThresholdsCatalog;
use InvalidArgumentException;

class SystemAutomationSettingsCatalog
{
    private const FIELD_OPTIONS = [
        'water_irrigation_decision_strategy' => ['task' => 'По расписанию', 'smart_soil_v1' => 'По влажности субстрата'],
        'water_irrigation_ec_component' => ['none' => 'Только pH, без коррекции EC', 'calcium' => 'pH и кальций', 'npk' => 'pH и NPK'],
        'water_system_type' => ['drip' => 'Капельный полив', 'substrate_trays' => 'Лотки с субстратом', 'nft' => 'Проточная система NFT'],
        'water_diagnostics_workflow' => ['startup' => 'Подготовка двух баков', 'cycle_start' => 'Подготовка цикла', 'diagnostics' => 'Только диагностика'],
    ];

    private const FIELD_CATALOG = [
        'pump_calibration' => [
            [
                'key' => 'pump_calibration',
                'label' => 'Калибровка насосов',
                'description' => 'Лимиты калибровки насосов и оценки её достоверности.',
                'fields' => [
                    ['path' => 'ml_per_sec_min', 'label' => 'Минимальная подача насоса, мл/с', 'description' => 'Минимальная допустимая скорость насоса.', 'type' => 'number', 'min' => 0.001, 'max' => 1.0, 'step' => 0.001],
                    ['path' => 'ml_per_sec_max', 'label' => 'Максимальная подача насоса, мл/с', 'description' => 'Максимальная допустимая скорость насоса.', 'type' => 'number', 'min' => 5.0, 'max' => 200.0, 'step' => 0.1],
                    ['path' => 'min_dose_ms', 'label' => 'Минимальный импульс дозирования, мс', 'description' => 'Минимальный эффективный импульс дозирования.', 'type' => 'integer', 'min' => 10, 'max' => 500],
                    ['path' => 'max_dose_ms', 'label' => 'Предельный импульс дозирования, мс', 'description' => 'Предельная длительность одной дозы. Должна совпадать с ограничением длительности команды в настройках устройства.', 'type' => 'integer', 'min' => 1000, 'max' => 300000],
                    ['path' => 'calibration_duration_min_sec', 'label' => 'Минимальный запуск для калибровки, сек', 'description' => 'Самый короткий запуск насоса, допустимый для калибровки.', 'type' => 'integer', 'min' => 1, 'max' => 10],
                    ['path' => 'calibration_duration_max_sec', 'label' => 'Максимальный запуск для калибровки, сек', 'description' => 'Предельная длительность запуска насоса при калибровке.', 'type' => 'integer', 'min' => 30, 'max' => 600],
                    ['path' => 'quality_score_basic', 'label' => 'Достоверность базовой калибровки, 0–1', 'description' => 'Достоверность калибровки только по измеренному объёму, без оценки отклика EC.', 'type' => 'number', 'min' => 0.0, 'max' => 1.0, 'step' => 0.01],
                    ['path' => 'quality_score_with_k', 'label' => 'Достоверность калибровки с откликом EC, 0–1', 'description' => 'Достоверность калибровки с измерением отклика EC на добавленный объём.', 'type' => 'number', 'min' => 0.0, 'max' => 1.0, 'step' => 0.01],
                    ['path' => 'quality_score_legacy', 'label' => 'Достоверность перенесённой калибровки, 0–1', 'description' => 'Достоверность калибровок, перенесённых из прежней версии.', 'type' => 'number', 'min' => 0.0, 'max' => 1.0, 'step' => 0.01],
                    ['path' => 'age_warning_days', 'label' => 'Возраст калибровки: предупреждение, дни', 'description' => 'Порог предупреждения по возрасту калибровки.', 'type' => 'integer', 'min' => 1, 'max' => 365],
                    ['path' => 'age_critical_days', 'label' => 'Возраст калибровки: критический, дни', 'description' => 'Критичный возраст калибровки.', 'type' => 'integer', 'min' => 7, 'max' => 365],
                    ['path' => 'default_run_duration_sec', 'label' => 'Начальная длительность калибровки, сек', 'description' => 'Начальная длительность запуска, предложенная в форме калибровки.', 'type' => 'integer', 'min' => 5, 'max' => 60],
                    ['path' => 'ml_per_sec_mismatch_pct', 'label' => 'Допустимое расхождение калибровок, %', 'description' => 'Насколько может различаться подача насоса в калибровке платформы и в настройках устройства.', 'type' => 'number', 'min' => 0.1, 'max' => 100.0, 'step' => 0.1],
                    ['path' => 'ml_per_sec_mismatch_fail_closed', 'label' => 'Блокировать дозирование при расхождении калибровок', 'description' => 'При включении дозирование запрещается, если калибровка в платформе расходится с настройкой устройства. При выключении остаётся предупреждение.', 'type' => 'boolean'],
                ],
            ],
        ],
        'sensor_calibration' => [
            [
                'key' => 'sensor_calibration',
                'label' => 'Калибровка сенсоров',
                'description' => 'Эталонные значения и сроки повторной калибровки pH/EC.',
                'fields' => [
                    ['path' => 'ph_point_1_value', 'label' => 'Первый эталон pH', 'description' => 'Рекомендуемый буфер для первой точки pH (Trema / iArduino: типично кислый, напр. 4.01).', 'type' => 'number', 'min' => 1.0, 'max' => 14.0, 'step' => 0.01],
                    ['path' => 'ph_point_2_value', 'label' => 'Второй эталон pH', 'description' => 'Рекомендуемый буфер для второй точки pH (Trema / iArduino: щелочной, напр. 9.18; точки должны заметно отличаться).', 'type' => 'number', 'min' => 1.0, 'max' => 14.0, 'step' => 0.01],
                    ['path' => 'ec_point_1_tds', 'label' => 'Первый эталон TDS, ppm', 'description' => 'Рекомендуемый TDS для первой точки EC.', 'type' => 'integer', 'min' => 100, 'max' => 10000],
                    ['path' => 'ec_point_2_tds', 'label' => 'Второй эталон TDS, ppm', 'description' => 'Рекомендуемый TDS для второй точки EC.', 'type' => 'integer', 'min' => 50, 'max' => 10000],
                    ['path' => 'reminder_days', 'label' => 'Напомнить о калибровке через, дни', 'description' => 'Через сколько дней напомнить о повторной калибровке.', 'type' => 'integer', 'min' => 7, 'max' => 365],
                    ['path' => 'critical_days', 'label' => 'Критический возраст калибровки, дни', 'description' => 'Через сколько дней считать калибровку критически устаревшей.', 'type' => 'integer', 'min' => 14, 'max' => 365],
                    ['path' => 'command_timeout_sec', 'label' => 'Ожидание ответа на калибровку, сек', 'description' => 'Сколько ждать подтверждения калибровки от устройства.', 'type' => 'integer', 'min' => 5, 'max' => 60],
                    ['path' => 'ph_reference_min', 'label' => 'Нижняя граница эталона pH', 'description' => 'Минимальное допустимое значение эталонного раствора pH.', 'type' => 'number', 'min' => 0.0, 'max' => 6.0, 'step' => 0.01],
                    ['path' => 'ph_reference_max', 'label' => 'Верхняя граница эталона pH', 'description' => 'Максимальное допустимое значение эталонного раствора pH.', 'type' => 'number', 'min' => 8.0, 'max' => 14.0, 'step' => 0.01],
                    ['path' => 'ec_tds_reference_max', 'label' => 'Верхняя граница эталона TDS, ppm', 'description' => 'Верхняя граница концентрации эталонного раствора для калибровки EC.', 'type' => 'integer', 'min' => 1000, 'max' => 20000],
                ],
            ],
        ],
        'process_calibration_defaults' => [
            [
                'key' => 'process_calibration_defaults',
                'label' => 'Калибровка процесса',
                'description' => 'Исходные оценки отклика раствора на добавление реагента.',
                'fields' => [
                    ['path' => 'transport_delay_sec', 'label' => 'Задержка отклика после дозы, сек', 'description' => 'Время от дозы до ожидаемого отклика на датчике.', 'type' => 'integer', 'min' => 0, 'max' => 120],
                    ['path' => 'settle_sec', 'label' => 'Ожидание стабилизации, сек', 'description' => 'Дополнительное окно для стабилизации измерений.', 'type' => 'integer', 'min' => 0, 'max' => 300],
                    ['path' => 'ec_gain_per_ml', 'label' => 'Прирост EC на 1 мл удобрения, мС/см', 'description' => 'Как меняется EC после добавления 1 мл удобрения.', 'type' => 'number', 'min' => 0.001, 'max' => 10.0, 'step' => 0.001],
                    ['path' => 'ph_up_gain_per_ml', 'label' => 'Повышение pH на 1 мл реагента', 'description' => 'На сколько повышается pH после добавления 1 мл повышающего реагента.', 'type' => 'number', 'min' => 0.001, 'max' => 5.0, 'step' => 0.001],
                    ['path' => 'ph_down_gain_per_ml', 'label' => 'Снижение pH на 1 мл реагента', 'description' => 'На сколько снижается pH после добавления 1 мл понижающего реагента.', 'type' => 'number', 'min' => 0.001, 'max' => 5.0, 'step' => 0.001],
                    ['path' => 'ph_per_ec_ml', 'label' => 'Изменение pH на 1 мл удобрения', 'description' => 'Побочное изменение pH после добавления 1 мл удобрения.', 'type' => 'number', 'min' => -2.0, 'max' => 2.0, 'step' => 0.001],
                    ['path' => 'ec_per_ph_ml', 'label' => 'Изменение EC на 1 мл реагента pH, мС/см', 'description' => 'Побочное изменение EC после добавления 1 мл реагента pH.', 'type' => 'number', 'min' => -2.0, 'max' => 2.0, 'step' => 0.001],
                    ['path' => 'confidence', 'label' => 'Достоверность исходной оценки, 0–1', 'description' => 'Начальная оценка доверия к системным рекомендованным значениям.', 'type' => 'number', 'min' => 0.0, 'max' => 1.0, 'step' => 0.01],
                ],
            ],
        ],
        'automation_defaults' => [
            [
                'key' => 'automation_profile_climate',
                'label' => 'Профиль климата по умолчанию',
                'description' => 'Исходные настройки климата для новых профилей.',
                'fields' => [
                    ['path' => 'climate_enabled', 'label' => 'Климат включён по умолчанию', 'description' => 'Включать управление климатом при создании нового профиля.', 'type' => 'boolean'],
                    ['path' => 'climate_day_temp_c', 'label' => 'Дневная температура, °C', 'description' => 'Дневная температура.', 'type' => 'number', 'min' => 10.0, 'max' => 35.0, 'step' => 0.1],
                    ['path' => 'climate_night_temp_c', 'label' => 'Ночная температура, °C', 'description' => 'Ночная температура.', 'type' => 'number', 'min' => 10.0, 'max' => 35.0, 'step' => 0.1],
                    ['path' => 'climate_day_humidity_pct', 'label' => 'Дневная влажность воздуха, %', 'description' => 'Дневная влажность.', 'type' => 'number', 'min' => 30.0, 'max' => 90.0, 'step' => 0.1],
                    ['path' => 'climate_night_humidity_pct', 'label' => 'Ночная влажность воздуха, %', 'description' => 'Ночная влажность.', 'type' => 'number', 'min' => 30.0, 'max' => 90.0, 'step' => 0.1],
                    ['path' => 'climate_interval_min', 'label' => 'Период проверки климата, мин', 'description' => 'Период климатического шага.', 'type' => 'integer', 'min' => 1, 'max' => 1440],
                    ['path' => 'climate_day_start_hhmm', 'label' => 'Начало дня, ЧЧ:ММ', 'description' => 'Начало дневного режима.', 'type' => 'string'],
                    ['path' => 'climate_night_start_hhmm', 'label' => 'Начало ночи, ЧЧ:ММ', 'description' => 'Начало ночного режима.', 'type' => 'string'],
                    ['path' => 'climate_vent_min_pct', 'label' => 'Минимальное открытие форточек, %', 'description' => 'Минимальное открытие форточек.', 'type' => 'integer', 'min' => 0, 'max' => 100],
                    ['path' => 'climate_vent_max_pct', 'label' => 'Максимальное открытие форточек, %', 'description' => 'Максимальное открытие форточек.', 'type' => 'integer', 'min' => 0, 'max' => 100],
                    ['path' => 'climate_use_external_telemetry', 'label' => 'Учитывать наружные датчики', 'description' => 'Учитывать наружную температуру и влажность при управлении вентиляцией.', 'type' => 'boolean'],
                    ['path' => 'climate_outside_temp_min_c', 'label' => 'Нижняя граница наружной температуры, °C', 'description' => 'Нижняя граница допустимой наружной температуры.', 'type' => 'number', 'min' => -30.0, 'max' => 45.0, 'step' => 0.1],
                    ['path' => 'climate_outside_temp_max_c', 'label' => 'Верхняя граница наружной температуры, °C', 'description' => 'Верхняя граница допустимой наружной температуры.', 'type' => 'number', 'min' => -30.0, 'max' => 45.0, 'step' => 0.1],
                    ['path' => 'climate_outside_humidity_max_pct', 'label' => 'Предельная наружная влажность, %', 'description' => 'Максимальная внешняя влажность.', 'type' => 'integer', 'min' => 20, 'max' => 100],
                    ['path' => 'climate_manual_override_enabled', 'label' => 'Разрешить временное ручное управление', 'description' => 'Разрешать оператору временно задавать управление вручную.', 'type' => 'boolean'],
                    ['path' => 'climate_manual_override_minutes', 'label' => 'Длительность ручного управления, мин', 'description' => 'Через сколько минут вернуть автоматическое управление после ручного изменения.', 'type' => 'integer', 'min' => 5, 'max' => 120],
                ],
            ],
            [
                'key' => 'automation_profile_water',
                'label' => 'Профиль воды и полива по умолчанию',
                'description' => 'Исходные настройки водного узла для новых профилей.',
                'fields' => [
                    ['path' => 'water_system_type', 'label' => 'Система полива по умолчанию', 'description' => 'Тип системы полива для нового профиля.', 'type' => 'string'],
                    ['path' => 'water_tanks_count', 'label' => 'Количество баков', 'description' => 'Количество баков по умолчанию.', 'type' => 'integer', 'min' => 2, 'max' => 3],
                    ['path' => 'water_clean_tank_fill_l', 'label' => 'Рабочий объём чистого бака, л', 'description' => 'Объём чистого бака.', 'type' => 'integer', 'min' => 10, 'max' => 5000],
                    ['path' => 'water_nutrient_tank_target_l', 'label' => 'Рабочий объём бака раствора, л', 'description' => 'Целевой объём бака раствора.', 'type' => 'integer', 'min' => 10, 'max' => 5000],
                    ['path' => 'water_irrigation_batch_l', 'label' => 'Ориентир объёма одной порции, л', 'description' => 'Справочный ориентир: фактическая подача ограничена длительностью, а объём рассчитывается по калибровке насоса.', 'type' => 'integer', 'min' => 1, 'max' => 500],
                    ['path' => 'water_interval_min', 'label' => 'Интервал проверки полива, мин', 'description' => 'Интервал между поливами.', 'type' => 'integer', 'min' => 1, 'max' => 1440],
                    ['path' => 'water_duration_sec', 'label' => 'Длительность одного полива, сек', 'description' => 'Длительность одного полива.', 'type' => 'integer', 'min' => 1, 'max' => 3600],
                    ['path' => 'water_fill_temperature_c', 'label' => 'Ориентир температуры набора, °C', 'description' => 'Справочное значение: не включает нагрев или охлаждение. Температурные ограничения полива задаются в рецепте.', 'type' => 'number', 'min' => 5.0, 'max' => 35.0, 'step' => 0.1],
                    ['path' => 'water_fill_window_start_hhmm', 'label' => 'Начало окна набора воды, ЧЧ:ММ', 'description' => 'Начало окна набора.', 'type' => 'string'],
                    ['path' => 'water_fill_window_end_hhmm', 'label' => 'Конец окна набора воды, ЧЧ:ММ', 'description' => 'Конец окна набора.', 'type' => 'string'],
                    ['path' => 'water_target_ph', 'label' => 'Исходная цель pH профиля', 'description' => 'Целевой pH.', 'type' => 'number', 'min' => 4.0, 'max' => 9.0, 'step' => 0.01],
                    ['path' => 'water_target_ec', 'label' => 'Исходная цель EC профиля, мС/см', 'description' => 'Целевой EC.', 'type' => 'number', 'min' => 0.1, 'max' => 10.0, 'step' => 0.01],
                    ['path' => 'water_ph_pct', 'label' => 'Допуск коррекции pH, %', 'description' => 'Процент допуска по pH.', 'type' => 'number', 'min' => 1.0, 'max' => 50.0, 'step' => 0.1],
                    ['path' => 'water_ec_pct', 'label' => 'Допуск коррекции EC, %', 'description' => 'Процент допуска по EC.', 'type' => 'number', 'min' => 1.0, 'max' => 50.0, 'step' => 0.1],
                    ['path' => 'water_valve_switching_enabled', 'label' => 'Переключать клапаны автоматически', 'description' => 'Разрешать переключение клапанов.', 'type' => 'boolean'],
                    ['path' => 'water_correction_during_irrigation', 'label' => 'Корректировать раствор во время полива', 'description' => 'Разрешать коррекцию pH и выбранного компонента EC во время полива.', 'type' => 'boolean'],
                    ['path' => 'water_irrigation_ec_component', 'label' => 'Коррекция EC во время полива', 'description' => 'Выберите только pH либо совместную коррекцию pH с кальцием или смесью NPK. Вариант «Только pH» не включает коррекцию EC.', 'type' => 'string'],
                    ['path' => 'water_drain_control_enabled', 'label' => 'Планировать долю дренажа', 'description' => 'Справочное значение для схемы с третьим баком; не включает автоматическое регулирование слива.', 'type' => 'boolean'],
                    ['path' => 'water_drain_target_pct', 'label' => 'Плановая доля дренажа, %', 'description' => 'Целевой дренаж.', 'type' => 'integer', 'min' => 0, 'max' => 100],
                    ['path' => 'water_diagnostics_enabled', 'label' => 'Включить диагностику водного контура', 'description' => 'Включать периодическую диагностику водного узла.', 'type' => 'boolean'],
                    ['path' => 'water_diagnostics_interval_min', 'label' => 'Период диагностики, мин', 'description' => 'Интервал между диагностическими проверками.', 'type' => 'integer', 'min' => 1, 'max' => 1440],
                    ['path' => 'water_cycle_start_workflow_enabled', 'label' => 'Подготавливать систему перед циклом', 'description' => 'Подготавливать водный узел перед началом работы.', 'type' => 'boolean'],
                    ['path' => 'water_diagnostics_workflow', 'label' => 'Сценарий диагностики', 'description' => 'Сценарий для запуска из интерфейса: подготовка системы, запуск цикла или диагностика.', 'type' => 'string'],
                    ['path' => 'water_clean_tank_full_threshold', 'label' => 'Порог полного чистого бака, 0–1', 'description' => 'Уровень, при котором бак чистой воды считается заполненным.', 'type' => 'number', 'min' => 0.05, 'max' => 1.0, 'step' => 0.01],
                    ['path' => 'water_refill_duration_sec', 'label' => 'Длительность долива, сек', 'description' => 'Длительность одного пополнения чистой воды.', 'type' => 'integer', 'min' => 1, 'max' => 3600],
                    ['path' => 'water_refill_timeout_sec', 'label' => 'Предельное ожидание долива, сек', 'description' => 'Предельное время ожидания завершения пополнения чистой воды.', 'type' => 'integer', 'min' => 30, 'max' => 86400],
                    ['path' => 'water_startup_clean_fill_timeout_sec', 'label' => 'Предельное время набора чистой воды, сек', 'description' => 'Предельное время набора чистой воды при подготовке системы.', 'type' => 'integer', 'min' => 30, 'max' => 86400],
                    ['path' => 'water_startup_solution_fill_timeout_sec', 'label' => 'Предельное время набора раствора, сек', 'description' => 'Предельное время набора раствора при подготовке системы.', 'type' => 'integer', 'min' => 30, 'max' => 86400],
                    ['path' => 'water_startup_prepare_recirculation_timeout_sec', 'label' => 'Предельное время перемешивания, сек', 'description' => 'Предельное время перемешивания и подготовки раствора.', 'type' => 'integer', 'min' => 30, 'max' => 86400],
                    ['path' => 'water_startup_clean_fill_retry_cycles', 'label' => 'Число повторов набора чистой воды', 'description' => 'Сколько повторных попыток набора чистой воды разрешено.', 'type' => 'integer', 'min' => 0, 'max' => 20],
                    ['path' => 'water_startup_level_poll_interval_sec', 'label' => 'Период проверки уровня, сек', 'description' => 'Как часто проверять уровень воды при подготовке системы.', 'type' => 'integer', 'min' => 5, 'max' => 3600],
                    ['path' => 'water_startup_level_switch_on_threshold', 'label' => 'Порог срабатывания датчика уровня, 0–1', 'description' => 'Значение, выше которого дискретный датчик уровня считается сработавшим.', 'type' => 'number', 'min' => 0.0, 'max' => 1.0, 'step' => 0.01],
                    ['path' => 'water_startup_clean_max_sensor_label', 'label' => 'Метка верхнего датчика чистого бака', 'description' => 'Название верхнего датчика уровня бака чистой воды. Должно точно совпадать с настройкой датчика.', 'type' => 'string'],
                    ['path' => 'water_startup_solution_max_sensor_label', 'label' => 'Метка верхнего датчика бака раствора', 'description' => 'Название верхнего датчика уровня бака раствора. Должно точно совпадать с настройкой датчика.', 'type' => 'string'],
                    ['path' => 'water_clean_fill_min_check_delay_ms', 'label' => 'Задержка проверки источника чистой воды, мс', 'description' => 'Задержка проверки нижнего уровня чистой воды после начала набора.', 'type' => 'integer', 'min' => 0, 'max' => 3600000],
                    ['path' => 'water_solution_fill_clean_min_check_delay_ms', 'label' => 'Задержка проверки источника при наборе раствора, мс', 'description' => 'Задержка проверки минимального уровня в чистом баке при наборе раствора.', 'type' => 'integer', 'min' => 0, 'max' => 3600000],
                    ['path' => 'water_solution_fill_solution_min_check_delay_ms', 'label' => 'Задержка проверки утечки раствора, мс', 'description' => 'Задержка проверки нижнего датчика раствора для обнаружения утечки при наборе.', 'type' => 'integer', 'min' => 0, 'max' => 3600000],
                    ['path' => 'water_recirculation_stop_on_solution_min', 'label' => 'Остановить перемешивание при низком уровне раствора', 'description' => 'Останавливать перемешивание при срабатывании нижнего уровня раствора.', 'type' => 'boolean'],
                    ['path' => 'water_estop_debounce_ms', 'label' => 'Фильтр дребезга аварийной кнопки, мс', 'description' => 'Время подавления дребезга контактов физической кнопки аварийной остановки.', 'type' => 'integer', 'min' => 20, 'max' => 5000],
                    ['path' => 'water_irrigation_decision_strategy', 'label' => 'Условие разрешения полива', 'description' => 'По расписанию — без проверки влажности. По влажности — при достаточной сухости и свежих корректных данных всех активных датчиков.', 'type' => 'string'],
                    ['path' => 'water_irrigation_decision_lookback_sec', 'label' => 'История влажности для решения, сек', 'description' => 'За какой период брать измерения влажности для решения о поливе.', 'type' => 'integer', 'min' => 60, 'max' => 86400],
                    ['path' => 'water_irrigation_decision_min_samples', 'label' => 'Желаемое число измерений влажности', 'description' => 'При меньшем числе свежих корректных измерений решение принимается с предупреждением; полив не запрещается автоматически.', 'type' => 'integer', 'min' => 1, 'max' => 100],
                    ['path' => 'water_irrigation_decision_stale_after_sec', 'label' => 'Максимальный возраст измерения влажности, сек', 'description' => 'Если у любого активного датчика нет корректного измерения моложе этого возраста, полив по влажности пропускается.', 'type' => 'integer', 'min' => 30, 'max' => 86400],
                    ['path' => 'water_irrigation_decision_hysteresis_pct', 'label' => 'Запас ниже нижней границы влажности, п.п.', 'description' => 'Вычитается из нижней границы влажности. Например, 40% минус 2 п.п. даёт порог запуска ниже 38%.', 'type' => 'number', 'min' => 0.0, 'max' => 100.0, 'step' => 0.1],
                    ['path' => 'water_irrigation_decision_spread_alert_threshold_pct', 'label' => 'Допустимый разброс датчиков влажности, п.п.', 'description' => 'Разница средних показаний датчиков, после которой требуется внимание. Предупреждение не запрещает полив.', 'type' => 'number', 'min' => 0.0, 'max' => 100.0, 'step' => 0.1],
                    ['path' => 'water_irrigation_stop_on_solution_min', 'label' => 'Остановить полив при низком уровне раствора', 'description' => 'Останавливать полив при нижнем уровне раствора.', 'type' => 'boolean'],
                    ['path' => 'water_irrigation_auto_replay_after_setup', 'label' => 'Повторить полив после подготовки раствора', 'description' => 'Повторять запрос полива после автоматической подготовки системы.', 'type' => 'boolean'],
                    ['path' => 'water_irrigation_max_setup_replays', 'label' => 'Максимум повторов полива после подготовки', 'description' => 'Максимальное число повторов запроса полива после автоматической подготовки.', 'type' => 'integer', 'min' => 0, 'max' => 10],
                    ['path' => 'water_prepare_tolerance_ec_pct', 'label' => 'Допуск EC при подготовке раствора, %', 'description' => 'Допустимое отклонение EC при подготовке раствора.', 'type' => 'number', 'min' => 0.1, 'max' => 100.0, 'step' => 0.1],
                    ['path' => 'water_prepare_tolerance_ph_pct', 'label' => 'Допуск pH при подготовке раствора, %', 'description' => 'Допустимое отклонение pH при подготовке раствора.', 'type' => 'number', 'min' => 0.1, 'max' => 100.0, 'step' => 0.1],
                    ['path' => 'water_correction_max_ec_attempts', 'label' => 'Максимум доз EC за окно коррекции', 'description' => 'Максимальное число попыток коррекции EC.', 'type' => 'integer', 'min' => 1, 'max' => 500],
                    ['path' => 'water_correction_max_ph_attempts', 'label' => 'Максимум доз pH за окно коррекции', 'description' => 'Максимальное число попыток коррекции pH.', 'type' => 'integer', 'min' => 1, 'max' => 500],
                    ['path' => 'water_correction_prepare_recirculation_max_attempts', 'label' => 'Максимум окон перемешивания при коррекции', 'description' => 'Количество окон перемешивания раствора.', 'type' => 'integer', 'min' => 1, 'max' => 50],
                    ['path' => 'water_correction_prepare_recirculation_max_correction_attempts', 'label' => 'Предельное число шагов коррекции при подготовке', 'description' => 'Предельное число проходов коррекции в одном окне перемешивания.', 'type' => 'integer', 'min' => 1, 'max' => 500],
                    ['path' => 'water_correction_stabilization_sec', 'label' => 'Стабилизация после коррекции, сек', 'description' => 'Пауза перед повторной проверкой результата коррекции.', 'type' => 'integer', 'min' => 0, 'max' => 3600],
                    ['path' => 'water_two_tank_irrigation_start_steps', 'label' => 'Число команд запуска полива', 'description' => 'Количество команд реле для запуска полива.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_irrigation_stop_steps', 'label' => 'Число команд остановки полива', 'description' => 'Количество команд реле для остановки полива.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_clean_fill_start_steps', 'label' => 'Число команд запуска набора чистой воды', 'description' => 'Количество команд реле для запуска набора чистой воды.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_clean_fill_stop_steps', 'label' => 'Число команд остановки набора чистой воды', 'description' => 'Количество команд реле для остановки набора чистой воды.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_solution_fill_start_steps', 'label' => 'Число команд запуска набора раствора', 'description' => 'Количество команд реле для запуска набора раствора.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_solution_fill_stop_steps', 'label' => 'Число команд остановки набора раствора', 'description' => 'Количество команд реле для остановки набора раствора.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_prepare_recirculation_start_steps', 'label' => 'Число команд запуска перемешивания', 'description' => 'Количество команд реле для запуска перемешивания и подготовки раствора.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_prepare_recirculation_stop_steps', 'label' => 'Число команд остановки перемешивания', 'description' => 'Количество команд реле для остановки перемешивания и подготовки раствора.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_irrigation_recovery_start_steps', 'label' => 'Число команд запуска восстановления полива', 'description' => 'Количество команд реле для запуска восстановления после полива.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_two_tank_irrigation_recovery_stop_steps', 'label' => 'Число команд остановки восстановления полива', 'description' => 'Количество команд реле для остановки восстановления после полива.', 'type' => 'integer', 'min' => 1, 'max' => 12],
                    ['path' => 'water_refill_required_node_types_csv', 'label' => 'Обязательные типы узлов для долива', 'description' => 'Обязательные типы устройств, перечисленные через запятую. Используйте идентификаторы типов из настроек устройств.', 'type' => 'string'],
                    ['path' => 'water_refill_preferred_channel', 'label' => 'Канал долива воды', 'description' => 'Предпочтительный канал устройства для пополнения чистой воды.', 'type' => 'string'],
                    ['path' => 'water_solution_change_enabled', 'label' => 'Включить плановую замену раствора', 'description' => 'Включать периодическую замену раствора в новом профиле.', 'type' => 'boolean'],
                    ['path' => 'water_solution_change_interval_min', 'label' => 'Интервал замены раствора, мин', 'description' => 'Интервал между заменами раствора.', 'type' => 'integer', 'min' => 1, 'max' => 1440],
                    ['path' => 'water_solution_change_duration_sec', 'label' => 'Длительность замены раствора, сек', 'description' => 'Длительность одного запуска замены раствора.', 'type' => 'integer', 'min' => 1, 'max' => 86400],
                    ['path' => 'water_manual_irrigation_sec', 'label' => 'Длительность ручного полива, сек', 'description' => 'Длительность ручного полива.', 'type' => 'integer', 'min' => 1, 'max' => 3600],
                ],
            ],
            [
                'key' => 'automation_profile_lighting',
                'label' => 'Профиль освещения по умолчанию',
                'description' => 'Исходные настройки освещения для новых профилей.',
                'fields' => [
                    ['path' => 'lighting_enabled', 'label' => 'Досветка включена по умолчанию', 'description' => 'Включать управление досветкой в новом профиле.', 'type' => 'boolean'],
                    ['path' => 'lighting_lux_day', 'label' => 'Дневная освещённость, лк', 'description' => 'Целевая дневная освещённость в люксах.', 'type' => 'integer', 'min' => 0, 'max' => 120000],
                    ['path' => 'lighting_lux_night', 'label' => 'Ночная освещённость, лк', 'description' => 'Целевая ночная освещённость в люксах.', 'type' => 'integer', 'min' => 0, 'max' => 120000],
                    ['path' => 'lighting_hours_on', 'label' => 'Продолжительность света, ч/сутки', 'description' => 'Длительность досветки.', 'type' => 'number', 'min' => 0.0, 'max' => 24.0, 'step' => 0.1],
                    ['path' => 'lighting_interval_min', 'label' => 'Период проверки освещения, мин', 'description' => 'Интервал проверки и регулировки освещения.', 'type' => 'integer', 'min' => 1, 'max' => 1440],
                    ['path' => 'lighting_schedule_start_hhmm', 'label' => 'Начало светового окна, ЧЧ:ММ', 'description' => 'Начало фотопериода.', 'type' => 'string'],
                    ['path' => 'lighting_schedule_end_hhmm', 'label' => 'Конец светового окна, ЧЧ:ММ', 'description' => 'Конец фотопериода.', 'type' => 'string'],
                    ['path' => 'lighting_manual_intensity_pct', 'label' => 'Яркость при ручном управлении, %', 'description' => 'Интенсивность освещения при временном ручном управлении.', 'type' => 'integer', 'min' => 0, 'max' => 100],
                    ['path' => 'lighting_manual_duration_hours', 'label' => 'Длительность ручного освещения, ч', 'description' => 'Через сколько минут вернуть автоматическое управление после ручного изменения.', 'type' => 'number', 'min' => 0.5, 'max' => 24.0, 'step' => 0.5],
                ],
            ],
        ],
        'automation_command_templates' => [
            [
                'key' => 'automation_command_templates',
                'label' => 'Последовательности команд оборудования',
                'description' => 'Шаблоны последовательностей команд реле для водного узла с двумя баками.',
                'fields' => [
                    ['path' => 'irrigation_start', 'label' => 'Запуск полива', 'description' => 'Последовательность команд реле для запуска полива.', 'type' => 'json'],
                    ['path' => 'irrigation_stop', 'label' => 'Остановка полива', 'description' => 'Последовательность команд реле для остановки полива.', 'type' => 'json'],
                    ['path' => 'clean_fill_start', 'label' => 'Начало набора чистой воды', 'description' => 'Последовательность команд реле для запуска набора чистой воды.', 'type' => 'json'],
                    ['path' => 'clean_fill_stop', 'label' => 'Остановка набора чистой воды', 'description' => 'Последовательность команд реле для остановки набора чистой воды.', 'type' => 'json'],
                    ['path' => 'solution_fill_start', 'label' => 'Начало набора раствора', 'description' => 'Последовательность команд реле для запуска набора раствора.', 'type' => 'json'],
                    ['path' => 'solution_fill_stop', 'label' => 'Остановка набора раствора', 'description' => 'Последовательность команд реле для остановки набора раствора.', 'type' => 'json'],
                    ['path' => 'prepare_recirculation_start', 'label' => 'Начало перемешивания раствора', 'description' => 'Последовательность команд реле для запуска перемешивания и подготовки раствора.', 'type' => 'json'],
                    ['path' => 'prepare_recirculation_stop', 'label' => 'Остановка перемешивания раствора', 'description' => 'Последовательность команд реле для остановки перемешивания и подготовки раствора.', 'type' => 'json'],
                    ['path' => 'irrigation_recovery_start', 'label' => 'Начало восстановления полива', 'description' => 'Последовательность команд реле для запуска восстановления после полива.', 'type' => 'json'],
                    ['path' => 'irrigation_recovery_stop', 'label' => 'Остановка восстановления полива', 'description' => 'Последовательность команд реле для остановки восстановления после полива.', 'type' => 'json'],
                ],
            ],
        ],
        'observability_thresholds' => [],
    ];

    public static function allDefaults(): array
    {
        return [
            'pump_calibration' => [
                'ml_per_sec_min' => 0.01,
                'ml_per_sec_max' => 20.0,
                'min_dose_ms' => 50,
                'max_dose_ms' => 60_000,
                'calibration_duration_min_sec' => 1,
                'calibration_duration_max_sec' => 120,
                'quality_score_basic' => 0.75,
                'quality_score_with_k' => 0.90,
                'quality_score_legacy' => 0.50,
                'age_warning_days' => 30,
                'age_critical_days' => 90,
                'default_run_duration_sec' => 20,
                'ml_per_sec_mismatch_pct' => 10.0,
                'ml_per_sec_mismatch_fail_closed' => true,
            ],
            'sensor_calibration' => [
                'ph_point_1_value' => 4.01,
                'ph_point_2_value' => 9.18,
                'ec_point_1_tds' => 1413,
                'ec_point_2_tds' => 707,
                'reminder_days' => 30,
                'critical_days' => 90,
                'command_timeout_sec' => 10,
                'ph_reference_min' => 1.0,
                'ph_reference_max' => 14.0,
                'ec_tds_reference_max' => 10000,
            ],
            'process_calibration_defaults' => [
                'ec_gain_per_ml' => 0.006,
                'ph_up_gain_per_ml' => 0.015,
                'ph_down_gain_per_ml' => 0.015,
                'ph_per_ec_ml' => -0.002,
                'ec_per_ph_ml' => 0.001,
                'transport_delay_sec' => 4,
                'settle_sec' => 12,
                'confidence' => 0.85,
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
                'water_irrigation_ec_component' => 'calcium',
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
                'water_startup_prepare_recirculation_timeout_sec' => 900,
                'water_startup_clean_fill_retry_cycles' => 1,
                'water_startup_level_poll_interval_sec' => 60,
                'water_startup_level_switch_on_threshold' => 0.5,
                'water_startup_clean_max_sensor_label' => 'level_clean_max',
                'water_startup_solution_max_sensor_label' => 'level_solution_max',
                'water_clean_fill_min_check_delay_ms' => 5000,
                'water_solution_fill_clean_min_check_delay_ms' => 5000,
                'water_solution_fill_solution_min_check_delay_ms' => 60000,
                'water_recirculation_stop_on_solution_min' => true,
                'water_estop_debounce_ms' => 80,
                'water_irrigation_decision_strategy' => 'task',
                'water_irrigation_decision_lookback_sec' => 1800,
                'water_irrigation_decision_min_samples' => 3,
                'water_irrigation_decision_stale_after_sec' => 600,
                'water_irrigation_decision_hysteresis_pct' => 2.0,
                'water_irrigation_decision_spread_alert_threshold_pct' => 12.0,
                'water_irrigation_stop_on_solution_min' => true,
                'water_irrigation_auto_replay_after_setup' => true,
                'water_irrigation_max_setup_replays' => 1,
                'water_prepare_tolerance_ec_pct' => 10.0,
                'water_prepare_tolerance_ph_pct' => 5.0,
                'water_correction_max_ec_attempts' => 8,
                'water_correction_max_ph_attempts' => 8,
                'water_correction_prepare_recirculation_max_attempts' => 4,
                'water_correction_prepare_recirculation_max_correction_attempts' => 40,
                'water_correction_stabilization_sec' => 8,
                'water_two_tank_irrigation_start_steps' => 3,
                'water_two_tank_irrigation_stop_steps' => 3,
                'water_two_tank_clean_fill_start_steps' => 1,
                'water_two_tank_clean_fill_stop_steps' => 1,
                'water_two_tank_solution_fill_start_steps' => 3,
                'water_two_tank_solution_fill_stop_steps' => 3,
                'water_two_tank_prepare_recirculation_start_steps' => 3,
                'water_two_tank_prepare_recirculation_stop_steps' => 3,
                'water_two_tank_irrigation_recovery_start_steps' => 4,
                'water_two_tank_irrigation_recovery_stop_steps' => 4,
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
                'irrigation_start' => [
                    ['channel' => 'valve_solution_supply', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'valve_irrigation', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                ],
                'irrigation_stop' => [
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_irrigation', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_solution_supply', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                ],
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
                    ['channel' => 'valve_irrigation', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                ],
            ],
        ];
    }

    public static function namespaces(): array
    {
        return array_values(array_unique([
            ...array_keys(self::FIELD_CATALOG),
            ObservabilityThresholdsCatalog::NAMESPACE_KEY,
        ]));
    }

    public static function defaults(string $namespace): array
    {
        if ($namespace === ObservabilityThresholdsCatalog::NAMESPACE_KEY) {
            return ObservabilityThresholdsCatalog::defaults();
        }

        $defaults = self::allDefaults();
        if (! array_key_exists($namespace, $defaults)) {
            throw new InvalidArgumentException("Unknown automation settings namespace: {$namespace}");
        }

        return $defaults[$namespace];
    }

    public static function fieldCatalog(string $namespace): array
    {
        if ($namespace === ObservabilityThresholdsCatalog::NAMESPACE_KEY) {
            return ObservabilityThresholdsCatalog::fieldCatalog();
        }

        if (! array_key_exists($namespace, self::FIELD_CATALOG)) {
            throw new InvalidArgumentException("Unknown automation settings namespace: {$namespace}");
        }

        $sections = self::FIELD_CATALOG[$namespace];
        foreach ($sections as &$section) {
            foreach ($section['fields'] as &$field) {
                if (isset(self::FIELD_OPTIONS[$field['path']])) {
                    $field['option_labels'] = self::FIELD_OPTIONS[$field['path']];
                    $field['options'] = array_keys($field['option_labels']);
                }
            }
        }
        unset($section, $field);

        return FieldCatalogHelpBuilder::attachHelp($sections, $namespace);
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
        if (isset($field['options']) && ! in_array($value, $field['options'], true)) {
            throw new InvalidArgumentException('Параметр «'.$field['label'].'»: выберите допустимый вариант из списка.');
        }
        if (str_ends_with($path, '_hhmm') && (! is_string($value) || ! preg_match('/^(?:[01]\d|2[0-3]):[0-5]\d$/', $value))) {
            throw new InvalidArgumentException('Параметр «'.$field['label'].'»: укажите время ЧЧ:ММ от 00:00 до 23:59.');
        }

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
            $minDoseMs = (int) ($effectiveConfig['min_dose_ms'] ?? 0);
            $maxDoseMs = (int) ($effectiveConfig['max_dose_ms'] ?? 0);
            $ageWarningDays = (int) ($effectiveConfig['age_warning_days'] ?? 0);
            $ageCriticalDays = (int) ($effectiveConfig['age_critical_days'] ?? 0);

            if ($mlPerSecMin > $mlPerSecMax) {
                throw new InvalidArgumentException('Field pump_calibration.ml_per_sec_min must be <= pump_calibration.ml_per_sec_max.');
            }
            if ($calibrationDurationMin > $calibrationDurationMax) {
                throw new InvalidArgumentException('Field pump_calibration.calibration_duration_min_sec must be <= pump_calibration.calibration_duration_max_sec.');
            }
            if ($maxDoseMs > 0 && $minDoseMs > 0 && $maxDoseMs < $minDoseMs) {
                throw new InvalidArgumentException('Field pump_calibration.max_dose_ms must be >= pump_calibration.min_dose_ms.');
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

            return;
        }

        if ($namespace === ObservabilityThresholdsCatalog::NAMESPACE_KEY) {
            ObservabilityThresholdsCatalog::validateConsistency($effectiveConfig);

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
