<?php

namespace Tests\Feature;

use App\Models\User;
use App\Services\AlertPolicyService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AlertPoliciesAutomationConfigTest extends TestCase
{
    use RefreshDatabase;

    public function test_authority_api_returns_default_alert_policy_document(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);

        $this->actingAs($admin)
            ->getJson('/api/automation-configs/system/0/system.alert_policies')
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.namespace', 'system.alert_policies')
            ->assertJsonPath('data.payload.ae3_operational_resolution_mode', AlertPolicyService::MODE_MANUAL_ACK);
    }

    public function test_authority_api_updates_alert_policy_document(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);

        $this->actingAs($admin)
            ->putJson('/api/automation-configs/system/0/system.alert_policies', [
                'payload' => [
                    'ae3_operational_resolution_mode' => AlertPolicyService::MODE_AUTO_RESOLVE_ON_RECOVERY,
                ],
            ])
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.payload.ae3_operational_resolution_mode', AlertPolicyService::MODE_AUTO_RESOLVE_ON_RECOVERY);
    }

    public function test_authority_api_rejects_invalid_alert_policy_value(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);

        $this->actingAs($admin)
            ->putJson('/api/automation-configs/system/0/system.alert_policies', [
                'payload' => [
                    'ae3_operational_resolution_mode' => 'something_else',
                ],
            ])
            ->assertStatus(422)
            ->assertJsonPath('status', 'error');
    }

    public function test_agronomist_can_update_alert_policy_document(): void
    {
        $agronomist = User::factory()->create(['role' => 'agronomist']);

        $this->actingAs($agronomist)
            ->putJson('/api/automation-configs/system/0/system.alert_policies', [
                'payload' => [
                    'ae3_operational_resolution_mode' => AlertPolicyService::MODE_AUTO_RESOLVE_ON_RECOVERY,
                ],
            ])
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.payload.ae3_operational_resolution_mode', AlertPolicyService::MODE_AUTO_RESOLVE_ON_RECOVERY);
    }

    public function test_telegram_test_ok_persists_and_survives_mode_only_save(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $documents = app(\App\Services\AutomationConfigDocumentService::class);

        $documents->upsertDocument(
            \App\Services\AutomationConfigRegistry::NAMESPACE_SYSTEM_ALERT_POLICIES,
            \App\Services\AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            [
                'ae3_operational_resolution_mode' => AlertPolicyService::MODE_MANUAL_ACK,
                'telegram_test_ok' => true,
                'telegram_test_at' => '2026-09-24T12:00:00+00:00',
            ],
            $admin->id,
            'alerts:telegram-test',
        );

        $this->actingAs($admin)
            ->putJson('/api/automation-configs/system/0/system.alert_policies', [
                'payload' => [
                    'ae3_operational_resolution_mode' => AlertPolicyService::MODE_AUTO_RESOLVE_ON_RECOVERY,
                ],
            ])
            ->assertOk()
            ->assertJsonPath('data.payload.ae3_operational_resolution_mode', AlertPolicyService::MODE_AUTO_RESOLVE_ON_RECOVERY)
            ->assertJsonPath('data.payload.telegram_test_ok', true)
            ->assertJsonPath('data.payload.telegram_test_at', '2026-09-24T12:00:00+00:00');
    }
}
