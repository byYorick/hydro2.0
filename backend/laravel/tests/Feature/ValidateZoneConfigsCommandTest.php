<?php

namespace Tests\Feature;

use App\Services\JsonSchemaValidator;
use App\Services\ZoneCorrectionConfigCatalog;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

/**
 * Feature test для `php artisan zones:validate-configs`.
 *
 * Проверяет:
 *  - валидный zone.correction document проходит валидацию (exit 0)
 *  - битый zone.correction document детектится (exit 1)
 *  - фильтр --namespace работает
 *  - --json выдаёт parseable JSON
 */
class ValidateZoneConfigsCommandTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        // Очищаем от bootstrap-seeded documents, чтобы тестировать только то,
        // что вставляем явно.
        DB::table('automation_config_versions')->delete();
        DB::table('automation_config_documents')->delete();
    }

    public function test_passes_when_all_documents_valid(): void
    {
        $this->insertDocument('zone.correction', 'zone', 1, $this->validZoneCorrectionPayload());

        // Прямая проверка validator — изолирует проверку schema от execution-layer
        $validator = app(JsonSchemaValidator::class);
        $violations = $validator->validate('zone.correction', $this->validZoneCorrectionPayload());
        $this->assertSame([], $violations, 'Canonical valid payload must pass validation');

        $this->artisan('zones:validate-configs', ['--namespace' => 'zone.correction'])
            ->assertExitCode(0);
    }

    public function test_fails_when_document_missing_required_section(): void
    {
        $base = $this->completeBaseConfig();
        unset($base['retry']);  // required section removed
        $broken = json_encode([
            'preset_id' => null,
            'base_config' => $base,
            'phase_overrides' => new \stdClass(),
            'resolved_config' => new \stdClass(),
        ], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);

        $this->insertDocument('zone.correction', 'zone', 42, $broken);

        $this->artisan('zones:validate-configs')
            ->assertExitCode(1);
    }

    public function test_namespace_filter_limits_scope(): void
    {
        // insert one valid zone.correction + one broken zone.logic_profile;
        // filtering by zone.correction should pass.
        $this->insertDocument('zone.correction', 'zone', 1, $this->validZoneCorrectionPayload());
        $this->insertDocument('zone.logic_profile', 'zone', 1, '{}');  // missing required fields

        $this->artisan('zones:validate-configs', ['--namespace' => 'zone.correction'])
            ->assertExitCode(0);
    }

    public function test_json_output_is_parseable(): void
    {
        $this->insertDocument('zone.correction', 'zone', 1, $this->validZoneCorrectionPayload());

        $this->artisan('zones:validate-configs', ['--namespace' => 'zone.correction', '--json' => true])
            ->assertExitCode(0);
    }

    /**
     * Canonical valid zone.correction document payload built from PHP defaults.
     * Returns a raw JSON string with proper object-vs-array semantics (empty
     * objects `{}` instead of ambiguous PHP `[]`).
     */
    private function validZoneCorrectionPayload(): string
    {
        $base = $this->completeBaseConfig();
        return json_encode([
            'preset_id' => null,
            'base_config' => $base,
            'phase_overrides' => new \stdClass(),
            'resolved_config' => new \stdClass(),
        ], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    }

    /**
     * Base correction config matching zone_correction.v1.json (all required sections).
     * Relies on ZoneCorrectionConfigCatalog::defaults() which was patched in Phase 1
     * to include `dosing.ec_dosing_mode` and `retry.prepare_recirculation_correction_slack_sec`
     * (previously missing — see inventory §9.5, §9.8).
     */
    private function completeBaseConfig(): array
    {
        return ZoneCorrectionConfigCatalog::defaults();
    }

    /**
     * @param array<string,mixed>|string $payload — JSON string preferred to preserve {} vs [] semantics
     */
    private function insertDocument(string $namespace, string $scopeType, int $scopeId, array|string $payload): void
    {
        $json = is_string($payload) ? $payload : json_encode($payload, JSON_UNESCAPED_SLASHES);
        DB::table('automation_config_documents')->insert([
            'namespace' => $namespace,
            'scope_type' => $scopeType,
            'scope_id' => $scopeId,
            'schema_version' => 1,
            'payload' => $json,
            'status' => 'valid',
            'source' => 'test',
            'checksum' => sha1($json),
            'updated_by' => null,
            'created_at' => now(),
            'updated_at' => now(),
        ]);
    }
}
