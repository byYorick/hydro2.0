<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Support\Facades\Event;
use Tests\RefreshDatabase;
use Tests\TestCase;

class UserPreferencesSettingsTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        Event::fake();
    }

    public function test_user_can_read_default_alert_suppression_preference(): void
    {
        $user = User::factory()->create([
            'preferences' => null,
        ]);

        $this->actingAs($user)
            ->getJson('/settings/preferences')
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.alert_toast_suppression_sec', 30);
    }

    public function test_user_can_update_alert_suppression_preference(): void
    {
        $user = User::factory()->create([
            'preferences' => [
                'alert_toast_suppression_sec' => 30,
            ],
        ]);

        $this->actingAs($user)
            ->patchJson('/settings/preferences', [
                'alert_toast_suppression_sec' => 45,
            ])
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.alert_toast_suppression_sec', 45);

        $this->assertSame(
            45,
            (int) ($user->fresh()->preferences['alert_toast_suppression_sec'] ?? 0)
        );
    }

    public function test_alert_suppression_preference_is_validated(): void
    {
        $user = User::factory()->create();

        $this->actingAs($user)
            ->patchJson('/settings/preferences', [
                'alert_toast_suppression_sec' => 1000,
            ])
            ->assertStatus(422)
            ->assertJsonValidationErrors(['alert_toast_suppression_sec']);
    }
}
