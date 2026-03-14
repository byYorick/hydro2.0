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
        ];
    }

    public static function namespaces(): array
    {
        return array_keys(self::allDefaults());
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
        }
    }
}
