<?php

namespace App\Services;

use Opis\JsonSchema\Errors\ErrorFormatter;
use Opis\JsonSchema\Resolvers\SchemaResolver;
use Opis\JsonSchema\Validator;
use RuntimeException;

/**
 * Wrapper вокруг opis/json-schema (поддерживает Draft 2020-12) для загрузки и
 * прогона payload через канонические JSON Schemas из schemas/ в корне репо.
 *
 * Contract:
 *  - schemas/ resolve-ится по приоритету: env AUTOMATION_SCHEMAS_ROOT → /schemas → base_path('../../schemas')
 *  - схемы именуются `<name>.vN.json` (например `zone_correction_document.v1.json`)
 *  - имена (без `.vN.json`) зашиты в NAMESPACE_SCHEMA_MAP
 *
 * validate() возвращает массив violations:
 *    [
 *      ['path' => 'retry.telemetry_stale_retry_sec', 'code' => 'required', 'message' => '...'],
 *      ...
 *    ]
 *
 * Cross-field constraints (например close_zone > dead_zone в zone.pid) НЕ
 * ловятся schema — их enforce Python-сторона (Pydantic) и/или отдельные
 * PHP-валидаторы в AutomationConfigRegistry.
 */
class JsonSchemaValidator
{
    private const NAMESPACE_SCHEMA_MAP = [
        'zone.correction' => 'zone_correction_document',
        'zone.pid.ph' => 'zone_pid',
        'zone.pid.ec' => 'zone_pid',
        'zone.process_calibration.generic' => 'zone_process_calibration',
        'zone.process_calibration.solution_fill' => 'zone_process_calibration',
        'zone.process_calibration.tank_recirc' => 'zone_process_calibration',
        'zone.process_calibration.irrigation' => 'zone_process_calibration',
        'zone.logic_profile' => 'zone_logic_profile',
        'system.automation_defaults' => 'system_automation_defaults',
    ];

    private string $schemasRoot;

    public function __construct(?string $schemasRoot = null)
    {
        $this->schemasRoot = $schemasRoot ?? self::defaultSchemasRoot();
    }

    private static function defaultSchemasRoot(): string
    {
        $override = getenv('AUTOMATION_SCHEMAS_ROOT');
        if (is_string($override) && $override !== '' && is_dir($override)) {
            return $override;
        }
        if (is_dir('/schemas')) {
            return '/schemas';
        }
        return base_path('../../schemas');
    }

    public function schemasRoot(): string
    {
        return $this->schemasRoot;
    }

    /**
     * @return list<string>
     */
    public function supportedNamespaces(): array
    {
        return array_keys(self::NAMESPACE_SCHEMA_MAP);
    }

    /**
     * Валидирует payload против канонической schema.
     *
     * @param string $namespace
     * @param array<string,mixed>|string $payload — либо PHP array, либо JSON string
     *   (предпочтительно string для сохранения object-vs-array семантики пустых `{}`).
     * @param int $schemaVersion
     * @return list<array{path:string,code:string,message:string}>
     */
    public function validate(string $namespace, array|string $payload, int $schemaVersion = 1): array
    {
        if (!isset(self::NAMESPACE_SCHEMA_MAP[$namespace])) {
            throw new RuntimeException("Unsupported namespace: {$namespace}");
        }
        if ($schemaVersion !== 1) {
            throw new RuntimeException("Only schema v1 supported, got v{$schemaVersion}");
        }

        $baseName = self::NAMESPACE_SCHEMA_MAP[$namespace];
        $schemaFile = "{$this->schemasRoot}/{$baseName}.v{$schemaVersion}.json";
        if (!is_file($schemaFile)) {
            throw new RuntimeException("Schema file missing: {$schemaFile}");
        }

        $validator = $this->buildValidator();
        $schemaId = "https://hydro2.local/schemas/{$baseName}/v{$schemaVersion}.json";

        if (is_string($payload)) {
            $payloadJson = $payload;
        } else {
            $payloadJson = json_encode($this->preserveObjects($payload), JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
            if ($payloadJson === false) {
                throw new RuntimeException("Cannot encode payload: " . json_last_error_msg());
            }
        }
        $payloadObject = json_decode($payloadJson, false);
        if ($payloadObject === null && json_last_error() !== JSON_ERROR_NONE) {
            throw new RuntimeException("Invalid JSON payload: " . json_last_error_msg());
        }

        $result = $validator->validate($payloadObject, $schemaId);
        if ($result->isValid()) {
            return [];
        }

        $formatter = new ErrorFormatter();
        $output = $formatter->formatOutput($result->error(), 'basic');

        $violations = [];
        foreach ($output['errors'] ?? [] as $err) {
            $violations[] = [
                'path' => $err['instanceLocation'] ?? '(root)',
                'code' => $err['keywordLocation'] ?? 'invalid',
                'message' => $err['error'] ?? 'unknown violation',
            ];
        }
        return $violations;
    }

    /**
     * Рекурсивно конвертирует пустые array `[]` (которые становятся JSON `[]`)
     * в stdClass (JSON `{}`), когда они представляют объект-по-смыслу.
     *
     * Эвристика: ассоциативный массив (есть string keys) → object; чистый list
     * (integer keys 0..N) → array. Пустой `[]` — неоднозначный, по умолчанию
     * трактуем как object (безопасно для config structures, где empty-object
     * встречается чаще, чем empty-list).
     *
     * @param mixed $value
     * @return mixed
     */
    private function preserveObjects(mixed $value): mixed
    {
        if (!is_array($value)) {
            return $value;
        }
        if (empty($value)) {
            return new \stdClass();
        }
        if (array_is_list($value)) {
            return array_map(fn($v) => $this->preserveObjects($v), $value);
        }
        $obj = new \stdClass();
        foreach ($value as $k => $v) {
            $obj->{(string) $k} = $this->preserveObjects($v);
        }
        return $obj;
    }

    private function buildValidator(): Validator
    {
        $validator = new Validator();
        /** @var SchemaResolver $resolver */
        $resolver = $validator->resolver();
        // File layout is `schemas/<name>.v<N>.json` (dot, not slash), so we register
        // each known schema file explicitly. $id in each schema uses the canonical URI
        // `https://hydro2.local/schemas/<name>/v<N>.json` (slash) — resolver maps URI → file.
        foreach (self::NAMESPACE_SCHEMA_MAP as $baseName) {
            $path = "{$this->schemasRoot}/{$baseName}.v1.json";
            if (is_file($path)) {
                $resolver->registerFile(
                    "https://hydro2.local/schemas/{$baseName}/v1.json",
                    $path,
                );
            }
        }
        // Register zone_correction base schema (referenced by document wrapper via $ref).
        $baseCorrection = "{$this->schemasRoot}/zone_correction.v1.json";
        if (is_file($baseCorrection)) {
            $resolver->registerFile(
                'https://hydro2.local/schemas/zone_correction/v1.json',
                $baseCorrection,
            );
        }
        return $validator;
    }
}
