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
}
