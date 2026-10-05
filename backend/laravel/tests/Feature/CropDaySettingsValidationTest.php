<?php

namespace Tests\Feature;

use App\Models\AutomationConfigDocument;
use App\Models\AutomationEffectiveBundle;
use App\Models\Greenhouse;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use App\Models\Zone;
use App\Services\AutomationConfigRegistry;
use Tests\RefreshDatabase;
use Tests\TestCase;

class CropDaySettingsValidationTest extends TestCase
{
    use RefreshDatabase;

    public function test_valid_phase_crop_day_fields_round_trip_and_empty_is_not_zero(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $phase = RecipeRevisionPhase::factory()->create([
            'dli_target' => null,
            'solution_temp_min' => null,
            'solution_temp_max' => null,
            'extensions' => [
                'day_night' => ['temperature' => ['day' => 22]],
            ],
        ]);

        $saved = $this->actingAs($user)
            ->patchJson("/api/recipe-revision-phases/{$phase->id}", [
                'solution_temp_min' => 18,
                'solution_temp_max' => 24,
                'dli_target' => 18.5,
                'extensions' => [
                    'day_night' => ['temperature' => ['day' => 22]],
                    'legacy_note' => 'keep',
                    'solution_health' => [
                        'required' => true,
                        'breach_hold_sec' => 900,
                    ],
                    'solution_max_age_days' => 14,
                    'solution_refresh_after_topup_ml' => 250.5,
                ],
            ]);

        $saved->assertOk()
            ->assertJsonPath('data.dli_target', 18.5)
            ->assertJsonPath('data.solution_temp_min', 18)
            ->assertJsonPath('data.solution_temp_max', 24)
            ->assertJsonPath('data.extensions.solution_health.required', true)
            ->assertJsonPath('data.extensions.solution_health.breach_hold_sec', 900)
            ->assertJsonPath('data.extensions.solution_max_age_days', 14)
            ->assertJsonPath('data.extensions.solution_refresh_after_topup_ml', 250.5)
            ->assertJsonPath('data.extensions.legacy_note', 'keep')
            ->assertJsonPath('data.extensions.day_night.temperature.day', 22);

        $phase->refresh();
        $this->assertEquals(18.5, (float) $phase->dli_target);
        $this->assertEquals(18.0, (float) $phase->solution_temp_min);
        $this->assertEquals(24.0, (float) $phase->solution_temp_max);
        $this->assertTrue(data_get($phase->extensions, 'solution_health.required'));
        $this->assertSame(900, data_get($phase->extensions, 'solution_health.breach_hold_sec'));
        $this->assertSame(14, data_get($phase->extensions, 'solution_max_age_days'));
        $this->assertEquals(250.5, data_get($phase->extensions, 'solution_refresh_after_topup_ml'));
        $this->assertSame('keep', data_get($phase->extensions, 'legacy_note'));

        $cleared = $this->actingAs($user)
            ->patchJson("/api/recipe-revision-phases/{$phase->id}", [
                'dli_target' => null,
                'extensions' => [
                    'day_night' => ['temperature' => ['day' => 22]],
                    'legacy_note' => 'keep',
                    'solution_health' => null,
                    'solution_max_age_days' => null,
                    'solution_refresh_after_topup_ml' => null,
                ],
            ]);

        $cleared->assertOk()
            ->assertJsonPath('data.dli_target', null)
            ->assertJsonPath('data.extensions.solution_health', null)
            ->assertJsonPath('data.extensions.solution_max_age_days', null)
            ->assertJsonPath('data.extensions.solution_refresh_after_topup_ml', null)
            ->assertJsonPath('data.extensions.legacy_note', 'keep');

        $phase->refresh();
        $this->assertNull($phase->dli_target);
        $this->assertNull(data_get($phase->extensions, 'solution_max_age_days'));
        $this->assertNull(data_get($phase->extensions, 'solution_refresh_after_topup_ml'));
        $this->assertNotSame(0, $phase->dli_target);
        $this->assertNotSame(0, data_get($phase->extensions, 'solution_max_age_days'));
    }

    public function test_invalid_phase_fields_do_not_write(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $phase = RecipeRevisionPhase::factory()->create([
            'dli_target' => 12.5,
            'solution_temp_min' => 18,
            'solution_temp_max' => 24,
            'extensions' => [
                'day_night' => ['temperature' => ['day' => 22]],
            ],
        ]);

        $cases = [
            ['dli_target' => 0],
            ['dli_target' => -1],
            ['solution_temp_min' => 25, 'solution_temp_max' => 19],
            [
                'solution_temp_min' => null,
                'solution_temp_max' => null,
                'extensions' => ['solution_health' => ['required' => true]],
            ],
            ['extensions' => ['solution_health' => ['breach_hold_sec' => 10]]],
            ['extensions' => ['solution_max_age_days' => 0]],
            ['extensions' => ['solution_refresh_after_topup_ml' => 0]],
        ];

        foreach ($cases as $payload) {
            $this->actingAs($user)
                ->patchJson("/api/recipe-revision-phases/{$phase->id}", $payload)
                ->assertStatus(422);

            $phase->refresh();
            $this->assertEquals(12.5, (float) $phase->dli_target);
            $this->assertEquals(18.0, (float) $phase->solution_temp_min);
            $this->assertEquals(24.0, (float) $phase->solution_temp_max);
            $this->assertSame(['day_night' => ['temperature' => ['day' => 22]]], $phase->extensions);
        }
    }

    public function test_valid_vpd_is_in_climate_bundle_and_empty_pair_is_not_zero(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $greenhouse = Greenhouse::factory()->create();
        $namespace = AutomationConfigRegistry::NAMESPACE_GREENHOUSE_LOGIC_PROFILE;

        $this->actingAs($user)
            ->putJson("/api/automation-configs/greenhouse/{$greenhouse->id}/{$namespace}", [
                'payload' => $this->climatePayload(0.1, 3.0),
            ])
            ->assertOk()
            ->assertJsonPath('data.payload.profiles.working.subsystems.climate.execution.greenhouse_targets.vpd_min_kpa', 0.1)
            ->assertJsonPath('data.payload.profiles.working.subsystems.climate.execution.greenhouse_targets.vpd_max_kpa', 3);

        $bundle = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_GREENHOUSE)
            ->where('scope_id', $greenhouse->id)
            ->firstOrFail();
        $targets = data_get($bundle->config, 'greenhouse.logic_profile.profiles.working.subsystems.climate.execution.greenhouse_targets');
        $this->assertEquals(0.1, data_get($targets, 'vpd_min_kpa'));
        $this->assertEquals(3.0, data_get($targets, 'vpd_max_kpa'));
        $this->assertEquals(18, data_get($targets, 'temp_min_c'));

        $this->actingAs($user)
            ->putJson("/api/automation-configs/greenhouse/{$greenhouse->id}/{$namespace}", [
                'payload' => $this->climatePayload(null, null),
            ])
            ->assertOk();

        $bundle->refresh();
        $cleared = data_get($bundle->config, 'greenhouse.logic_profile.profiles.working.subsystems.climate.execution.greenhouse_targets');
        $this->assertNull(data_get($cleared, 'vpd_min_kpa'));
        $this->assertNull(data_get($cleared, 'vpd_max_kpa'));
        $this->assertNotSame(0, data_get($cleared, 'vpd_min_kpa'));
        $this->assertNotSame(0, data_get($cleared, 'vpd_max_kpa'));
    }

    public function test_invalid_vpd_does_not_write_document(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $greenhouse = Greenhouse::factory()->create();
        $namespace = AutomationConfigRegistry::NAMESPACE_GREENHOUSE_LOGIC_PROFILE;

        $this->actingAs($user)
            ->putJson("/api/automation-configs/greenhouse/{$greenhouse->id}/{$namespace}", [
                'payload' => $this->climatePayload(0.8, 1.4),
            ])
            ->assertOk();

        $before = AutomationConfigDocument::query()
            ->where('namespace', $namespace)
            ->where('scope_type', AutomationConfigRegistry::SCOPE_GREENHOUSE)
            ->where('scope_id', $greenhouse->id)
            ->firstOrFail();
        $checksum = $before->checksum;

        $onlyMin = $this->climatePayload(1.2, null);
        unset($onlyMin['profiles']['working']['subsystems']['climate']['execution']['greenhouse_targets']['vpd_max_kpa']);

        $cases = [
            $this->climatePayload(1.8, 0.4),
            $onlyMin,
            $this->climatePayload(0, 1.2),
        ];

        foreach ($cases as $payload) {
            $this->actingAs($user)
                ->putJson("/api/automation-configs/greenhouse/{$greenhouse->id}/{$namespace}", [
                    'payload' => $payload,
                ])
                ->assertStatus(422)
                ->assertJsonPath('status', 'error');
        }

        $before->refresh();
        $this->assertSame($checksum, $before->checksum);
        $this->assertEquals(0.8, data_get($before->payload, 'profiles.working.subsystems.climate.execution.greenhouse_targets.vpd_min_kpa'));
        $this->assertEquals(1.4, data_get($before->payload, 'profiles.working.subsystems.climate.execution.greenhouse_targets.vpd_max_kpa'));
    }

    public function test_zone_profile_keeps_legacy_irrigation_keys_without_new_fields(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();
        $namespace = AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE;

        $response = $this->actingAs($admin)
            ->putJson("/api/automation-configs/zone/{$zone->id}/{$namespace}", [
                'payload' => [
                    'active_mode' => 'working',
                    'profiles' => [
                        'working' => [
                            'custom_flag' => true,
                            'subsystems' => [
                                'irrigation' => [
                                    'enabled' => true,
                                    'decision' => [
                                        'strategy' => 'smart_soil_v1',
                                        'config' => [
                                            'lookback_sec' => 15,
                                            'hysteresis_pct' => 2.5,
                                            'legacy_marker' => 'keep',
                                        ],
                                    ],
                                ],
                            ],
                            'command_plans' => [
                                'schema_version' => 1,
                                'plan_version' => 1,
                                'plans' => [],
                            ],
                        ],
                        'setup' => [
                            'subsystems' => [
                                'diagnostics' => [
                                    'enabled' => true,
                                    'execution' => ['workflow' => 'cycle_start'],
                                ],
                            ],
                        ],
                    ],
                ],
            ]);

        $response->assertOk()
            ->assertJsonPath('data.payload.profiles.working.custom_flag', true)
            ->assertJsonPath('data.payload.profiles.working.subsystems.irrigation.decision.strategy', 'smart_soil_v1')
            ->assertJsonPath('data.payload.profiles.working.subsystems.irrigation.decision.config.lookback_sec', 15)
            ->assertJsonPath('data.payload.profiles.working.subsystems.irrigation.decision.config.hysteresis_pct', 2.5)
            ->assertJsonPath('data.payload.profiles.working.subsystems.irrigation.decision.config.legacy_marker', 'keep')
            ->assertJsonPath('data.payload.profiles.working.command_plans.schema_version', 1);

        $bundle = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->firstOrFail();
        $this->assertSame(
            'smart_soil_v1',
            data_get($bundle->config, 'zone.logic_profile.active_profile.subsystems.irrigation.decision.strategy')
        );
        $this->assertSame(
            15,
            data_get($bundle->config, 'zone.logic_profile.active_profile.subsystems.irrigation.decision.config.lookback_sec')
        );
        $this->assertSame(
            'keep',
            data_get($bundle->config, 'zone.logic_profile.active_profile.subsystems.irrigation.decision.config.legacy_marker')
        );
    }

    public function test_unknown_irrigation_strategy_does_not_write(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();
        $namespace = AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE;
        $valid = [
            'active_mode' => 'working',
            'profiles' => [
                'working' => [
                    'subsystems' => [
                        'irrigation' => [
                            'enabled' => true,
                            'decision' => [
                                'strategy' => 'task',
                                'config' => ['lookback_sec' => 1800, 'hysteresis_pct' => 2],
                            ],
                        ],
                    ],
                ],
            ],
        ];

        $this->actingAs($admin)
            ->putJson("/api/automation-configs/zone/{$zone->id}/{$namespace}", ['payload' => $valid])
            ->assertOk();

        $document = AutomationConfigDocument::query()
            ->where('namespace', $namespace)
            ->where('scope_id', $zone->id)
            ->firstOrFail();
        $checksum = $document->checksum;

        $invalid = $valid;
        $invalid['profiles']['working']['subsystems']['irrigation']['decision']['strategy'] = 'moisture_v2';

        $this->actingAs($admin)
            ->putJson("/api/automation-configs/zone/{$zone->id}/{$namespace}", ['payload' => $invalid])
            ->assertStatus(422)
            ->assertJsonPath('status', 'error');

        $document->refresh();
        $this->assertSame($checksum, $document->checksum);
        $this->assertSame('task', data_get($document->payload, 'profiles.working.subsystems.irrigation.decision.strategy'));
        $this->assertSame(1800, data_get($document->payload, 'profiles.working.subsystems.irrigation.decision.config.lookback_sec'));
    }

    public function test_viewer_still_cannot_update_crop_day_settings(): void
    {
        $viewer = User::factory()->create(['role' => 'viewer']);
        $phase = RecipeRevisionPhase::factory()->create(['dli_target' => 4]);
        $zone = Zone::factory()->create();
        $greenhouse = Greenhouse::factory()->create();

        $this->actingAs($viewer)
            ->patchJson("/api/recipe-revision-phases/{$phase->id}", ['dli_target' => 8])
            ->assertForbidden();
        $phase->refresh();
        $this->assertEquals(4.0, (float) $phase->dli_target);

        $this->actingAs($viewer)
            ->putJson('/api/automation-configs/zone/'.$zone->id.'/'.AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE, [
                'payload' => ['active_mode' => 'working', 'profiles' => []],
            ])
            ->assertForbidden();
        $this->assertDatabaseMissing('automation_config_documents', [
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
            'scope_type' => 'zone',
            'scope_id' => $zone->id,
        ]);

        $this->actingAs($viewer)
            ->putJson('/api/automation-configs/greenhouse/'.$greenhouse->id.'/'.AutomationConfigRegistry::NAMESPACE_GREENHOUSE_LOGIC_PROFILE, [
                'payload' => $this->climatePayload(0.8, 1.2),
            ])
            ->assertForbidden();
        $this->assertDatabaseMissing('automation_config_documents', [
            'namespace' => AutomationConfigRegistry::NAMESPACE_GREENHOUSE_LOGIC_PROFILE,
            'scope_type' => 'greenhouse',
            'scope_id' => $greenhouse->id,
        ]);
    }

    /**
     * @return array<string, mixed>
     */
    private function climatePayload(mixed $vpdMin, mixed $vpdMax): array
    {
        return [
            'active_mode' => 'working',
            'profiles' => [
                'working' => [
                    'subsystems' => [
                        'climate' => [
                            'enabled' => true,
                            'execution' => [
                                'strategy' => 'greenhouse_runtime',
                                'greenhouse_targets' => [
                                    'temp_min_c' => 18,
                                    'temp_max_c' => 28,
                                    'humidity_min_pct' => 45,
                                    'humidity_max_pct' => 80,
                                    'vpd_min_kpa' => $vpdMin,
                                    'vpd_max_kpa' => $vpdMax,
                                ],
                            ],
                        ],
                    ],
                ],
            ],
        ];
    }
}
