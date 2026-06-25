<?php

namespace Tests\Feature;

use App\Models\User;
use App\Support\Automation\ObservabilityThresholdsCatalog;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ObservabilityThresholdsAutomationConfigTest extends TestCase
{
    use RefreshDatabase;

    public function test_system_observability_thresholds_document_returns_field_catalog(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);

        $this->actingAs($admin)
            ->getJson('/api/automation-configs/system/0/system.observability_thresholds')
            ->assertOk()
            ->assertJsonPath('data.namespace', 'system.observability_thresholds')
            ->assertJsonPath('data.meta.field_catalog.0.key', 'observability_commands')
            ->assertJsonPath('data.payload.waiting_command_warn_sec', 120)
            ->assertJsonStructure([
                'data' => [
                    'meta' => [
                        'field_catalog' => [
                            [
                                'help',
                                'fields' => [
                                    ['help'],
                                ],
                            ],
                        ],
                    ],
                ],
            ]);
    }

    public function test_system_observability_thresholds_rejects_warn_greater_than_critical(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $defaults = ObservabilityThresholdsCatalog::defaults();
        $defaults['waiting_command_warn_sec'] = 500;
        $defaults['waiting_command_critical_sec'] = 120;

        $this->actingAs($admin)
            ->putJson('/api/automation-configs/system/0/system.observability_thresholds', [
                'payload' => $defaults,
            ])
            ->assertStatus(422);
    }

    public function test_system_observability_thresholds_update_persists_values(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $defaults = ObservabilityThresholdsCatalog::defaults();
        $defaults['waiting_command_warn_sec'] = 150;

        $this->actingAs($admin)
            ->putJson('/api/automation-configs/system/0/system.observability_thresholds', [
                'payload' => $defaults,
            ])
            ->assertOk()
            ->assertJsonPath('data.payload.waiting_command_warn_sec', 150);
    }

    public function test_agronomist_can_update_system_observability_thresholds(): void
    {
        $agronomist = User::factory()->create(['role' => 'agronomist']);
        $defaults = ObservabilityThresholdsCatalog::defaults();
        $defaults['waiting_command_warn_sec'] = 165;

        $this->actingAs($agronomist)
            ->putJson('/api/automation-configs/system/0/system.observability_thresholds', [
                'payload' => $defaults,
            ])
            ->assertOk()
            ->assertJsonPath('data.payload.waiting_command_warn_sec', 165);
    }
}
