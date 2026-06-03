<?php

namespace Tests\Unit;

use App\Services\ErrorCodeCatalogService;
use Tests\TestCase;

class ErrorCodeCatalogServiceTest extends TestCase
{
    private ErrorCodeCatalogService $catalog;

    protected function setUp(): void
    {
        parent::setUp();
        $this->catalog = app(ErrorCodeCatalogService::class);
    }

    public function test_error_payload_includes_human_error_message(): void
    {
        $payload = $this->catalog->errorPayload('not_found');

        $this->assertSame('error', $payload['status']);
        $this->assertSame('not_found', $payload['code']);
        $this->assertSame($payload['message'], $payload['human_error_message']);
        $this->assertNotEmpty($payload['message']);
        $this->assertMatchesRegularExpression('/[А-Яа-яЁё]/u', (string) $payload['human_error_message']);
    }

    public function test_normalize_code_converts_upper_snake_to_lower(): void
    {
        $this->assertSame('cycle_already_active', $this->catalog->normalizeCode('CYCLE_ALREADY_ACTIVE'));
    }

    public function test_enrich_error_payload_localizes_upstream_ae3_body(): void
    {
        $enriched = $this->catalog->enrichErrorPayload([
            'status' => 'error',
            'code' => 'ae3_task_create_conflict',
            'message' => 'ae3_task_create_conflict',
        ]);

        $this->assertSame('ae3_task_create_conflict', $enriched['code']);
        $this->assertSame($enriched['message'], $enriched['human_error_message']);
        $this->assertMatchesRegularExpression('/[А-Яа-яЁё]/u', (string) $enriched['human_error_message']);
    }

    public function test_localize_response_payload_translates_unauthorized(): void
    {
        $localized = $this->catalog->localizeResponsePayload([
            'status' => 'error',
            'message' => 'Unauthorized',
        ]);

        $this->assertSame('unauthenticated', $localized['code']);
        $this->assertSame($localized['message'], $localized['human_error_message']);
        $this->assertMatchesRegularExpression('/[А-Яа-яЁё]/u', (string) $localized['human_error_message']);
    }

    public function test_present_keeps_unknown_english_when_no_catalog_match(): void
    {
        $presentation = $this->catalog->present('unknown_xyz', 'Custom upstream failure');

        $this->assertSame('Custom upstream failure', $presentation['message']);
    }

    public function test_present_firmware_command_response_codes_in_russian(): void
    {
        foreach (['invalid_signature', 'timestamp_expired', 'pump_in_cooldown', 'solution_fill_timeout'] as $code) {
            $presentation = $this->catalog->present($code);
            $this->assertSame($code, $presentation['code']);
            $this->assertMatchesRegularExpression('/[А-Яа-яЁё]/u', (string) $presentation['message']);
        }
    }

    public function test_enrich_error_payload_handles_command_response_error_code_field(): void
    {
        $enriched = $this->catalog->enrichErrorPayload([
            'status' => 'error',
            'error_code' => 'hmac_required',
            'message' => 'hmac_required',
        ]);

        $this->assertSame('hmac_required', $enriched['error_code']);
        $this->assertArrayHasKey('human_error_message', $enriched);
        $this->assertMatchesRegularExpression('/[А-Яа-яЁё]/u', (string) $enriched['human_error_message']);
    }

    public function test_enrich_error_payload_handles_fastapi_detail_object(): void
    {
        $enriched = $this->catalog->enrichErrorPayload([
            'detail' => [
                'status' => 'error',
                'code' => 'irr_state_unavailable',
                'message' => 'irr_state_unavailable',
            ],
        ]);

        $this->assertSame('irr_state_unavailable', $enriched['detail']['code']);
        $this->assertArrayHasKey('human_error_message', $enriched['detail']);
        $this->assertMatchesRegularExpression(
            '/[А-Яа-яЁё]/u',
            (string) $enriched['detail']['human_error_message'],
        );
    }
}
