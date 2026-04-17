<?php

namespace Tests\Unit;

use App\Services\ZoneCorrectionConfigCatalog;
use Tests\TestCase;

/**
 * Verifies that ZoneCorrectionConfigCatalog::defaults() matches the
 * canonical schemas/zone_correction_defaults.json file.
 *
 * This is the PHP-side CI gate for Phase 5 (AE_LEGACY_CLEANUP_PLAN.md):
 * if defaults() drifts from the JSON file, this test fails.
 */
class ZoneCorrectionCatalogDefaultsTest extends TestCase
{
    private function loadJsonDefaults(): array
    {
        $path = base_path('../../../../schemas/zone_correction_defaults.json');

        // Fallback: try relative to project root.
        if (! file_exists($path)) {
            $path = base_path('../../../schemas/zone_correction_defaults.json');
        }

        // Walk up from the laravel directory to find the schemas folder.
        if (! file_exists($path)) {
            $dir = base_path();
            for ($i = 0; $i < 5; $i++) {
                $candidate = $dir.'/schemas/zone_correction_defaults.json';
                if (file_exists($candidate)) {
                    $path = $candidate;
                    break;
                }
                $dir = dirname($dir);
            }
        }

        $this->assertFileExists($path, 'schemas/zone_correction_defaults.json not found relative to Laravel base_path');

        $decoded = json_decode(file_get_contents($path), true);
        $this->assertIsArray($decoded, 'zone_correction_defaults.json must decode to an array');

        return $decoded;
    }

    public function test_defaults_match_json_schema_defaults(): void
    {
        $phpDefaults = ZoneCorrectionConfigCatalog::defaults();
        $jsonDefaults = $this->loadJsonDefaults();

        $this->assertSameRecursive($phpDefaults, $jsonDefaults);
    }

    public function test_defaults_contain_all_required_sections(): void
    {
        $defaults = ZoneCorrectionConfigCatalog::defaults();
        $required = ['controllers', 'runtime', 'timing', 'dosing', 'retry', 'tolerance', 'safety'];

        foreach ($required as $section) {
            $this->assertArrayHasKey($section, $defaults, "defaults() must contain section '{$section}'");
        }
    }

    public function test_ec_dosing_mode_enum_includes_multi_sequential(): void
    {
        $catalog = ZoneCorrectionConfigCatalog::fieldCatalog();

        $ecDosingField = null;
        foreach ($catalog as $section) {
            foreach ($section['fields'] as $field) {
                if ($field['path'] === 'dosing.ec_dosing_mode') {
                    $ecDosingField = $field;
                    break 2;
                }
            }
        }

        $this->assertNotNull($ecDosingField, 'dosing.ec_dosing_mode must exist in fieldCatalog');
        $this->assertContains('multi_sequential', $ecDosingField['options'], 'ec_dosing_mode must accept multi_sequential (legacy value per JSON Schema)');
    }

    /**
     * Recursively compare two arrays, asserting equality for all leaf values.
     * Uses delta comparison for floats.
     */
    private function assertSameRecursive(array $expected, array $actual, string $path = ''): void
    {
        $this->assertSame(
            array_keys($expected),
            array_keys($actual),
            "Keys differ at '{$path}': expected [".implode(', ', array_keys($expected)).'] got ['.implode(', ', array_keys($actual)).']'
        );

        foreach ($expected as $key => $expectedValue) {
            $currentPath = $path === '' ? (string) $key : "{$path}.{$key}";

            if (is_array($expectedValue)) {
                $this->assertIsArray($actual[$key], "'{$currentPath}' must be an array");
                $this->assertSameRecursive($expectedValue, $actual[$key], $currentPath);
                continue;
            }

            if (is_float($expectedValue)) {
                $this->assertEqualsWithDelta(
                    $expectedValue,
                    $actual[$key],
                    1e-9,
                    "Float mismatch at '{$currentPath}'"
                );
                continue;
            }

            $this->assertSame($expectedValue, $actual[$key], "Value mismatch at '{$currentPath}'");
        }
    }
}
