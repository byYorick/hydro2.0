<?php

namespace App\Support\Automation;

class FieldCatalogHelpBuilder
{
    /**
     * @param  list<array{key:string,label:string,description:string,fields:list<array<string,mixed>>}>  $catalog
     * @return list<array{key:string,label:string,description:string,fields:list<array<string,mixed>>}>
     */
    public static function attachHelp(array $catalog, string $namespace): array
    {
        foreach ($catalog as &$section) {
            if (! isset($section['help']) && ! empty($section['description'])) {
                $section['help'] = self::buildSectionHelp($namespace, $section);
            }

            foreach ($section['fields'] as &$field) {
                if (! isset($field['help'])) {
                    $field['help'] = self::buildFieldHelp($namespace, $field);
                }
            }
        }
        unset($section, $field);

        return $catalog;
    }

    /**
     * @param  array{key?:string,label?:string,description?:string}  $section
     */
    private static function buildSectionHelp(string $namespace, array $section): string
    {
        $label = (string) ($section['label'] ?? $section['key'] ?? 'Раздел');
        $description = (string) ($section['description'] ?? '');

        $lines = [
            $description,
            "Раздел «{$label}» группирует связанные системные параметры namespace `{$namespace}`.",
            'Изменения сохраняются в authority-документе и попадают в automation bundle после публикации конфигурации.',
        ];

        return self::joinParagraphs($lines);
    }

    /**
     * @param  array<string, mixed>  $field
     */
    public static function buildFieldHelp(string $namespace, array $field): string
    {
        $path = (string) ($field['path'] ?? '');
        $label = (string) ($field['label'] ?? $path);
        $description = (string) ($field['description'] ?? '');
        $type = (string) ($field['type'] ?? 'string');

        $lines = [];

        if ($description !== '') {
            $lines[] = $description;
        }

        if ($namespace === 'automation_command_templates' && $type === 'json') {
            $lines[] = 'Шаблон — упорядоченный список команд `set_relay` для two-tank workflow. AE3 выполняет шаги последовательно при входе в соответствующую фазу.';
            $lines[] = 'Поле «Канал» должно совпадать с именем ACTUATOR-канала в NodeConfig узла полива (например `pump_main`, `valve_irrigation`).';
            $lines[] = 'Состояние ON/OFF задаёт `params.state` команды. Порядок шагов важен: сначала открываются клапаны, затем насос, при остановке — наоборот.';
            $lines[] = 'После сохранения значение применяется через system automation bundle; для уже запущенных задач может потребоваться новый цикл workflow.';

            return self::joinParagraphs($lines);
        }

        if ($namespace === ObservabilityThresholdsCatalog::NAMESPACE_KEY) {
            $lines[] = 'Порог задаёт момент появления diagnostic hint в UI зоны (warning или critical). Значение warning всегда должно быть меньше critical.';
            $lines[] = 'AE3 использует пороги на live-path; Laravel — при stale fallback пересборки automation state из БД.';
            if (str_contains($path, '_warn_sec')) {
                $lines[] = 'Уровень warning — ранний сигнал для оператора: процесс ещё может завершиться штатно, но уже дольше ожидаемого.';
            }
            if (str_contains($path, '_critical_sec')) {
                $lines[] = 'Уровень critical — ситуация требует внимания: вероятна блокировка workflow, потеря telemetry или зависшая команда.';
            }

            return self::joinParagraphs($lines);
        }

        $typeHint = match ($type) {
            'boolean' => 'Булевый параметр: определяет, включена ли функция по умолчанию в системных рекомендациях и UI.',
            'integer', 'number' => 'Числовой параметр: используется валидацией authority и подсказками UI.',
            'string' => 'Строковый параметр: обычно идентификатор канала, режима или время в формате HH:MM.',
            'json' => 'JSON-структура: редактируйте только если понимаете контракт automation runtime.',
            default => null,
        };
        if ($typeHint !== null) {
            $lines[] = $typeHint;
        }

        if (isset($field['min'], $field['max'])) {
            $unit = isset($field['unit']) ? ' '.(string) $field['unit'] : '';
            $lines[] = 'Допустимый диапазон: от '.(string) $field['min'].' до '.(string) $field['max'].$unit.'. Значения вне диапазона API отклонит при сохранении.';
        }

        $namespaceContext = match ($namespace) {
            'pump_calibration' => 'Влияет на системные лимиты калибровки насосов: UI мастера калибровки, проверку ml/сек и качества калибровки во всех зонах.',
            'sensor_calibration' => 'Рекомендуемые эталоны для мастера калибровки pH/EC и пороги напоминаний о просроченной калибровке.',
            'process_calibration_defaults' => 'Стартовые коэффициенты process calibration UI (ожидаемый отклик датчиков на дозу, задержки транспорта и стабилизации).',
            'automation_defaults' => 'Системные дефолты для мастера автоматики и пресетов зоны: климат, вода, освещение. Не переопределяют активный рецепт зоны.',
            default => 'Системный параметр authority `system.*`: применяется как источник истины для runtime helpers и UI.',
        };
        $lines[] = $namespaceContext;

        $lines[] = "Технический ключ поля: `{$path}`.";

        return self::joinParagraphs($lines);
    }

    /**
     * @param  list<string|null>  $lines
     */
    private static function joinParagraphs(array $lines): string
    {
        return implode(
            "\n\n",
            array_values(array_filter(array_map(
                static fn (?string $line) => is_string($line) && trim($line) !== '' ? trim($line) : null,
                $lines
            )))
        );
    }
}
