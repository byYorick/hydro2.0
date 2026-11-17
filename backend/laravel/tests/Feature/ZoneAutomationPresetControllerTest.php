<?php

namespace Tests\Feature;

use App\Models\AutomationConfigPreset;
use App\Models\User;
use App\Models\ZoneAutomationPreset;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationPresetControllerTest extends TestCase
{
    use RefreshDatabase;

    private function validPayload(array $overrides = []): array
    {
        return array_merge([
            'name' => 'My Custom DWC',
            'description' => 'Пользовательский профиль для DWC',
            'tanks_count' => 2,
            'irrigation_system_type' => 'dwc',
            'correction_preset_id' => null,
            'correction_profile' => 'balanced',
            'config' => [
                'irrigation' => [
                    'duration_sec' => 300,
                    'interval_sec' => 3600,
                    'correction_during_irrigation' => true,
                    'correction_slack_sec' => 30,
                ],
                'irrigation_decision' => [
                    'strategy' => 'task',
                ],
                'startup' => [
                    'clean_fill_timeout_sec' => 1200,
                    'solution_fill_timeout_sec' => 1800,
                    'prepare_recirculation_timeout_sec' => 1200,
                    'level_poll_interval_sec' => 60,
                    'clean_fill_retry_cycles' => 1,
                ],
                'climate' => null,
                'lighting' => null,
            ],
        ], $overrides);
    }

    // --- List ---

    public function test_list_returns_all_presets(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $baseCount = ZoneAutomationPreset::query()->count();

        ZoneAutomationPreset::query()->create([
            'name' => 'Custom One',
            'slug' => 'custom-one',
            'scope' => 'custom',
            'tanks_count' => 2,
            'irrigation_system_type' => 'dwc',
            'config' => [],
            'created_by' => $user->id,
        ]);

        $this->actingAs($user)
            ->getJson('/api/zone-automation-presets')
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonCount($baseCount + 1, 'data');
    }

    public function test_list_filters_by_tanks_count(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);

        ZoneAutomationPreset::query()->create([
            'name' => 'Three Tank Custom', 'slug' => 'three-tank-custom', 'scope' => 'custom',
            'tanks_count' => 3, 'irrigation_system_type' => 'dwc', 'config' => [],
        ]);

        $response = $this->actingAs($user)
            ->getJson('/api/zone-automation-presets?tanks_count=3')
            ->assertOk();

        $data = collect($response->json('data'));
        $this->assertTrue($data->every(fn ($p) => $p['tanks_count'] === 3));
        $this->assertTrue($data->contains(fn ($p) => $p['slug'] === 'three-tank-custom'));
    }

    public function test_list_filters_by_irrigation_system_type(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);

        ZoneAutomationPreset::query()->create([
            'name' => 'Ebb Flow Custom', 'slug' => 'ebb-flow-custom', 'scope' => 'custom',
            'tanks_count' => 2, 'irrigation_system_type' => 'ebb_flow', 'config' => [],
        ]);

        $response = $this->actingAs($user)
            ->getJson('/api/zone-automation-presets?irrigation_system_type=ebb_flow')
            ->assertOk();

        $data = collect($response->json('data'));
        $this->assertTrue($data->every(fn ($p) => $p['irrigation_system_type'] === 'ebb_flow'));
        $this->assertTrue($data->contains(fn ($p) => $p['slug'] === 'ebb-flow-custom'));
    }

    public function test_list_system_presets_sorted_first(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);

        ZoneAutomationPreset::query()->create([
            'name' => 'Zzz Custom', 'slug' => 'zzz-sort-test', 'scope' => 'custom',
            'tanks_count' => 2, 'irrigation_system_type' => 'dwc', 'config' => [],
        ]);

        $response = $this->actingAs($user)
            ->getJson('/api/zone-automation-presets')
            ->assertOk();

        $data = collect($response->json('data'));
        $systemCount = $data->where('scope', 'system')->count();
        $this->assertGreaterThan(0, $systemCount);

        // system presets all come before custom
        $firstCustomIndex = $data->search(fn ($p) => $p['scope'] === 'custom');
        $lastSystemIndex = $data->reverse()->search(fn ($p) => $p['scope'] === 'system');
        $lastSystemIndex = $data->count() - 1 - $lastSystemIndex;
        $this->assertGreaterThan($lastSystemIndex, $firstCustomIndex);
    }

    // --- Show ---

    public function test_show_returns_single_preset(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);

        $preset = ZoneAutomationPreset::query()->create([
            'name' => 'Test', 'slug' => 'test-show', 'scope' => 'custom',
            'tanks_count' => 2, 'irrigation_system_type' => 'dwc', 'config' => ['irrigation' => ['duration_sec' => 300]],
        ]);

        $this->actingAs($user)
            ->getJson("/api/zone-automation-presets/{$preset->id}")
            ->assertOk()
            ->assertJsonPath('data.name', 'Test')
            ->assertJsonPath('data.config.irrigation.duration_sec', 300);
    }

    public function test_show_returns_404_for_missing(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);

        $this->actingAs($user)
            ->getJson('/api/zone-automation-presets/999999')
            ->assertNotFound();
    }

    // --- Create ---

    public function test_create_custom_preset(): void
    {
        $user = User::factory()->create(['role' => 'operator']);

        $this->actingAs($user)
            ->postJson('/api/zone-automation-presets', $this->validPayload())
            ->assertCreated()
            ->assertJsonPath('data.name', 'My Custom DWC')
            ->assertJsonPath('data.scope', 'custom')
            ->assertJsonPath('data.is_locked', false)
            ->assertJsonPath('data.tanks_count', 2)
            ->assertJsonPath('data.irrigation_system_type', 'dwc')
            ->assertJsonPath('data.correction_profile', 'balanced')
            ->assertJsonPath('data.config.irrigation.duration_sec', 300);

        $this->assertDatabaseHas('zone_automation_presets', [
            'name' => 'My Custom DWC',
            'scope' => 'custom',
            'created_by' => $user->id,
        ]);
    }

    public function test_create_with_correction_preset_id(): void
    {
        $user = User::factory()->create(['role' => 'operator']);

        $correctionPreset = AutomationConfigPreset::query()->create([
            'namespace' => 'zone.correction',
            'scope' => 'system',
            'is_locked' => true,
            'name' => 'Balanced',
            'slug' => 'balanced-test',
            'payload' => [],
        ]);

        $this->actingAs($user)
            ->postJson('/api/zone-automation-presets', $this->validPayload([
                'correction_preset_id' => $correctionPreset->id,
            ]))
            ->assertCreated()
            ->assertJsonPath('data.correction_preset_id', $correctionPreset->id);
    }

    public function test_create_validates_required_fields(): void
    {
        $user = User::factory()->create(['role' => 'operator']);

        $this->actingAs($user)
            ->postJson('/api/zone-automation-presets', [])
            ->assertUnprocessable()
            ->assertJsonValidationErrors(['name', 'tanks_count', 'irrigation_system_type', 'config']);
    }

    public function test_create_validates_irrigation_system_type_enum(): void
    {
        $user = User::factory()->create(['role' => 'operator']);

        $this->actingAs($user)
            ->postJson('/api/zone-automation-presets', $this->validPayload([
                'irrigation_system_type' => 'invalid_type',
            ]))
            ->assertUnprocessable()
            ->assertJsonValidationErrors(['irrigation_system_type']);
    }

    public function test_create_validates_config_ranges(): void
    {
        $user = User::factory()->create(['role' => 'operator']);

        $payload = $this->validPayload();
        $payload['config']['irrigation']['duration_sec'] = 0;
        $payload['config']['startup']['clean_fill_timeout_sec'] = 99999;

        $this->actingAs($user)
            ->postJson('/api/zone-automation-presets', $payload)
            ->assertUnprocessable()
            ->assertJsonValidationErrors([
                'config.irrigation.duration_sec',
                'config.startup.clean_fill_timeout_sec',
            ]);
    }

    public function test_create_requires_operator_role(): void
    {
        $viewer = User::factory()->create(['role' => 'viewer']);

        $this->actingAs($viewer)
            ->postJson('/api/zone-automation-presets', $this->validPayload())
            ->assertForbidden();
    }

    // --- Update ---

    public function test_update_custom_preset(): void
    {
        $user = User::factory()->create(['role' => 'operator']);

        $preset = ZoneAutomationPreset::query()->create([
            'name' => 'Old Name', 'slug' => 'old-name', 'scope' => 'custom',
            'tanks_count' => 2, 'irrigation_system_type' => 'dwc', 'config' => [],
            'created_by' => $user->id,
        ]);

        $this->actingAs($user)
            ->putJson("/api/zone-automation-presets/{$preset->id}", [
                'name' => 'New Name',
                'description' => 'Обновлённое описание',
            ])
            ->assertOk()
            ->assertJsonPath('data.name', 'New Name')
            ->assertJsonPath('data.description', 'Обновлённое описание');
    }

    public function test_update_system_preset_rejected(): void
    {
        $user = User::factory()->create(['role' => 'admin']);

        $preset = ZoneAutomationPreset::query()->create([
            'name' => 'System', 'slug' => 'sys', 'scope' => 'system', 'is_locked' => true,
            'tanks_count' => 2, 'irrigation_system_type' => 'dwc', 'config' => [],
        ]);

        $this->actingAs($user)
            ->putJson("/api/zone-automation-presets/{$preset->id}", ['name' => 'Hacked'])
            ->assertUnprocessable()
            ->assertJsonPath('message', 'System presets are read-only.');
    }

    // --- Delete ---

    public function test_delete_custom_preset(): void
    {
        $user = User::factory()->create(['role' => 'operator']);

        $preset = ZoneAutomationPreset::query()->create([
            'name' => 'ToDelete', 'slug' => 'to-delete', 'scope' => 'custom',
            'tanks_count' => 2, 'irrigation_system_type' => 'dwc', 'config' => [],
        ]);

        $this->actingAs($user)
            ->deleteJson("/api/zone-automation-presets/{$preset->id}")
            ->assertOk();

        $this->assertDatabaseMissing('zone_automation_presets', ['id' => $preset->id]);
    }

    public function test_delete_system_preset_rejected(): void
    {
        $user = User::factory()->create(['role' => 'admin']);

        $preset = ZoneAutomationPreset::query()->create([
            'name' => 'System', 'slug' => 'sys-del', 'scope' => 'system', 'is_locked' => true,
            'tanks_count' => 2, 'irrigation_system_type' => 'dwc', 'config' => [],
        ]);

        $this->actingAs($user)
            ->deleteJson("/api/zone-automation-presets/{$preset->id}")
            ->assertUnprocessable();

        $this->assertDatabaseHas('zone_automation_presets', ['id' => $preset->id]);
    }

    // --- Duplicate ---

    public function test_duplicate_creates_copy(): void
    {
        $user = User::factory()->create(['role' => 'operator']);

        $preset = ZoneAutomationPreset::query()->create([
            'name' => 'Original', 'slug' => 'original', 'scope' => 'system', 'is_locked' => true,
            'tanks_count' => 2, 'irrigation_system_type' => 'dwc',
            'correction_profile' => 'balanced',
            'config' => ['irrigation' => ['duration_sec' => 300]],
        ]);

        $this->actingAs($user)
            ->postJson("/api/zone-automation-presets/{$preset->id}/duplicate")
            ->assertCreated()
            ->assertJsonPath('data.scope', 'custom')
            ->assertJsonPath('data.is_locked', false)
            ->assertJsonPath('data.correction_profile', 'balanced')
            ->assertJsonPath('data.config.irrigation.duration_sec', 300);

        $this->assertDatabaseHas('zone_automation_presets', [
            'scope' => 'custom',
            'correction_profile' => 'balanced',
        ]);
    }

    // --- System presets from migration ---

    public function test_system_presets_exist_after_migration(): void
    {
        $expectedSlugs = [
            'dwc-balanced',
            'dwc-safe',
            'dwc-aggressive',
            'drip-tape-balanced',
            'drip-tape-safe',
            'drip-tape-aggressive',
            'nft-balanced',
            'nft-safe',
            'nft-aggressive',
            'test-node-automation',
        ];

        foreach ($expectedSlugs as $slug) {
            $this->assertDatabaseHas('zone_automation_presets', [
                'slug' => $slug,
                'scope' => 'system',
                'is_locked' => true,
            ]);
        }
    }

    public function test_system_presets_have_config_structure(): void
    {
        $preset = ZoneAutomationPreset::query()
            ->where('slug', 'dwc-balanced')
            ->firstOrFail();

        $config = $preset->config;

        $this->assertIsArray($config);
        $this->assertArrayHasKey('irrigation', $config);
        $this->assertArrayHasKey('irrigation_decision', $config);
        $this->assertArrayHasKey('startup', $config);

        $this->assertArrayHasKey('duration_sec', $config['irrigation']);
        $this->assertArrayHasKey('interval_sec', $config['irrigation']);
        $this->assertArrayHasKey('strategy', $config['irrigation_decision']);
        $this->assertArrayHasKey('clean_fill_timeout_sec', $config['startup']);
    }

    public function test_system_presets_have_correction_preset_links(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);

        $response = $this->actingAs($user)
            ->getJson('/api/zone-automation-presets')
            ->assertOk();

        $systemPresets = collect($response->json('data'))
            ->where('scope', 'system');

        foreach ($systemPresets as $preset) {
            $this->assertNotNull($preset['correction_profile'], "Preset {$preset['slug']} has null correction_profile");
        }
    }
    public function test_presets_accept_runtime_compatible_irrigation_boundaries(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $payload = $this->validPayload();
        $payload['config']['irrigation']['duration_sec'] = 1;
        $payload['config']['irrigation']['irrigation_ec_component'] = 'none';
        $payload['config']['irrigation_decision'] = [
            'strategy' => 'smart_soil_v1',
            'config' => ['stale_after_sec' => 30, 'hysteresis_pct' => 80, 'min_samples' => 1],
        ];
        $this->actingAs($user)->postJson('/api/zone-automation-presets', $payload)
            ->assertCreated()
            ->assertJsonPath('data.config.irrigation.irrigation_ec_component', 'none')
            ->assertJsonPath('data.config.irrigation_decision.config.stale_after_sec', 30);
    }

    public function test_invalid_partial_preset_update_does_not_corrupt_saved_configuration(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $config = $this->validPayload()['config'];
        $preset = ZoneAutomationPreset::query()->create([
            'name' => 'Validation fixture', 'slug' => 'validation-fixture', 'scope' => 'custom',
            'tanks_count' => 2, 'irrigation_system_type' => 'dwc', 'config' => $config, 'created_by' => $user->id,
        ]);
        foreach ([['min_samples' => 0], ['min_samples' => 1.5], ['stale_after_sec' => 29], ['hysteresis_pct' => 101]] as $invalid) {
            $this->actingAs($user)->putJson("/api/zone-automation-presets/{$preset->id}", [
                'config' => ['irrigation_decision' => ['config' => $invalid]],
            ])->assertUnprocessable();
            $this->assertEquals($config, $preset->fresh()->config);
        }
        $this->actingAs($user)->putJson("/api/zone-automation-presets/{$preset->id}", [
            'config' => ['irrigation' => ['duration_sec' => 3601]],
        ])->assertUnprocessable();
    }

}
