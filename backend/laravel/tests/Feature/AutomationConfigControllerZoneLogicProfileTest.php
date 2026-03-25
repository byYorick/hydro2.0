<?php

namespace Tests\Feature;

use App\Models\AutomationEffectiveBundle;
use App\Models\User;
use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AutomationConfigControllerZoneLogicProfileTest extends TestCase
{
    use RefreshDatabase;

    public function test_update_regenerates_command_plans_for_zone_logic_profile_documents(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        $payload = [
            'active_mode' => 'setup',
            'profiles' => [
                'setup' => [
                    'mode' => 'setup',
                    'is_active' => true,
                    'subsystems' => [
                        'diagnostics' => [
                            'enabled' => true,
                            'execution' => [
                                'workflow' => 'startup',
                                'two_tank_commands' => [
                                    'clean_fill_start' => [
                                        [
                                            'channel' => 'valve_clean_fill',
                                            'cmd' => 'set_relay',
                                            'params' => ['state' => true],
                                        ],
                                    ],
                                ],
                            ],
                        ],
                        'irrigation' => [
                            'enabled' => true,
                            'execution' => [
                                'system_type' => 'substrate_trays',
                            ],
                        ],
                    ],
                    'updated_at' => '2026-03-25T06:41:19Z',
                ],
            ],
        ];

        $response = $this->actingAs($admin)
            ->putJson("/api/automation-configs/zone/{$zone->id}/zone.logic_profile", [
                'payload' => $payload,
            ]);

        $response
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.payload.profiles.setup.command_plans.schema_version', 1)
            ->assertJsonPath('data.payload.profiles.setup.command_plans.source', 'automation_logic_profile_document_normalized')
            ->assertJsonPath('data.payload.profiles.setup.command_plans.plans.diagnostics.execution.workflow', 'cycle_start');

        $steps = $response->json('data.payload.profiles.setup.command_plans.plans.diagnostics.steps');
        $this->assertIsArray($steps);
        $this->assertCount(1, $steps);
        $this->assertSame('valve_clean_fill', $steps[0]['channel'] ?? null);

        $documentPayload = app(AutomationConfigDocumentService::class)->getPayload(
            AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            false
        );

        $this->assertSame(
            'cycle_start',
            data_get($documentPayload, 'profiles.setup.command_plans.plans.diagnostics.execution.workflow')
        );
        $this->assertCount(
            1,
            data_get($documentPayload, 'profiles.setup.command_plans.plans.diagnostics.steps', [])
        );

        $bundle = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->firstOrFail();

        $this->assertSame(
            1,
            data_get($bundle->config, 'zone.logic_profile.active_profile.command_plans.schema_version')
        );
        $this->assertCount(
            1,
            data_get($bundle->config, 'zone.logic_profile.active_profile.command_plans.plans.diagnostics.steps', [])
        );
    }

    public function test_update_rejects_invalid_two_tank_command_contract(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        $payload = [
            'active_mode' => 'setup',
            'profiles' => [
                'setup' => [
                    'mode' => 'setup',
                    'is_active' => true,
                    'subsystems' => [
                        'diagnostics' => [
                            'enabled' => true,
                            'execution' => [
                                'workflow' => 'cycle_start',
                                'topology' => 'two_tank_drip_substrate_trays',
                                'two_tank_commands' => [
                                    'solution_fill_start' => [
                                        [
                                            'channel' => 'valve_clean_supply',
                                            'cmd' => 'set_relay',
                                            'params' => ['state' => true],
                                        ],
                                    ],
                                ],
                            ],
                        ],
                    ],
                ],
            ],
        ];

        $response = $this->actingAs($admin)
            ->putJson("/api/automation-configs/zone/{$zone->id}/zone.logic_profile", [
                'payload' => $payload,
            ]);

        $response
            ->assertStatus(422)
            ->assertJsonPath('status', 'error');

        $this->assertStringContainsString(
            'two_tank_commands.solution_fill_start',
            (string) $response->json('message')
        );
        $this->assertStringContainsString(
            'valve_solution_fill',
            (string) $response->json('message')
        );
        $this->assertStringContainsString(
            'pump_main',
            (string) $response->json('message')
        );
    }
}
