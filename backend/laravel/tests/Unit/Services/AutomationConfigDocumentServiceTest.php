<?php

namespace Tests\Unit\Services;

use App\Models\AutomationConfigPreset;
use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\ZoneCorrectionConfigCatalog;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AutomationConfigDocumentServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_zone_correction_normalizer_uses_current_system_pump_calibration_policy(): void
    {
        $documents = app(AutomationConfigDocumentService::class);
        $zone = Zone::factory()->create();

        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            [
                'ml_per_sec_min' => 0.02,
                'ml_per_sec_max' => 12.5,
                'min_dose_ms' => 125,
                'calibration_duration_min_sec' => 2,
                'calibration_duration_max_sec' => 90,
                'quality_score_basic' => 0.70,
                'quality_score_with_k' => 0.90,
                'quality_score_legacy' => 0.50,
                'age_warning_days' => 20,
                'age_critical_days' => 60,
                'default_run_duration_sec' => 15,
            ]
        );

        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            [
                'preset_id' => null,
                'base_config' => ZoneCorrectionConfigCatalog::defaults(),
                'phase_overrides' => [],
            ]
        );

        $payload = $documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id
        );

        $this->assertSame(125, data_get($payload, 'resolved_config.pump_calibration.min_dose_ms'));
        $this->assertSame(0.02, data_get($payload, 'resolved_config.pump_calibration.ml_per_sec_min'));
        $this->assertSame(12.5, data_get($payload, 'resolved_config.pump_calibration.ml_per_sec_max'));
    }

    public function test_zone_correction_normalizer_applies_preset_to_resolved_config(): void
    {
        $documents = app(AutomationConfigDocumentService::class);
        $zone = Zone::factory()->create();
        $preset = AutomationConfigPreset::query()->create([
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            'scope' => 'system',
            'is_locked' => false,
            'name' => 'Correction preset',
            'slug' => 'correction-preset',
            'description' => 'test',
            'schema_version' => 1,
            'payload' => [
                'base' => [
                    'timing' => [
                        'stabilization_sec' => 321,
                    ],
                ],
                'phases' => [],
            ],
            'updated_by' => null,
        ]);

        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            [
                'preset_id' => $preset->id,
                'base_config' => ZoneCorrectionConfigCatalog::defaults(),
                'phase_overrides' => [],
            ]
        );

        $payload = $documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id
        );

        $this->assertSame($preset->id, data_get($payload, 'resolved_config.meta.preset_id'));
        $this->assertSame('correction-preset', data_get($payload, 'resolved_config.meta.preset_slug'));
        $this->assertSame('Correction preset', data_get($payload, 'resolved_config.meta.preset_name'));
    }
}
