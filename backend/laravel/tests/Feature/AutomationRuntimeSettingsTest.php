<?php

namespace Tests\Feature;

use App\Models\AutomationRuntimeOverride;
use App\Models\User;
use App\Services\AutomationRuntimeConfigService;
use Inertia\Testing\AssertableInertia;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Event;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AutomationRuntimeSettingsTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        Event::fake();
    }

    public function test_admin_can_read_runtime_settings_snapshot(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);

        $response = $this->actingAs($admin)->getJson('/settings/automation-engine');

        $response
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonStructure([
                'status',
                'data' => [
                    'generated_at',
                    'sections' => [
                        '*' => [
                            'key',
                            'title',
                            'items',
                        ],
                    ],
                ],
            ]);

        $item = $this->findSettingItem($response->json('data.sections'), 'automation_engine.scheduler_due_grace_sec');
        $this->assertNotNull($item);
        $this->assertSame('default', $item['source']);
    }

    public function test_viewer_cannot_modify_runtime_settings(): void
    {
        $viewer = User::factory()->create(['role' => 'viewer']);

        $this->actingAs($viewer)
            ->patchJson('/settings/automation-engine', [
                'settings' => [
                    'automation_engine.scheduler_due_grace_sec' => 35,
                ],
            ])
            ->assertForbidden();
    }

    public function test_admin_patch_applies_overrides_immediately(): void
    {
        Config::set('services.automation_engine.scheduler_due_grace_sec', 15);
        Config::set('services.automation_engine.scheduler_catchup_policy', 'replay_limited');

        $admin = User::factory()->create(['role' => 'admin']);

        $response = $this->actingAs($admin)
            ->patchJson('/settings/automation-engine', [
                'settings' => [
                    'automation_engine.scheduler_due_grace_sec' => 45,
                    'automation_engine.scheduler_catchup_policy' => 'skip',
                ],
            ]);

        $response->assertOk()->assertJsonPath('status', 'ok');

        $item = $this->findSettingItem($response->json('data.sections'), 'automation_engine.scheduler_due_grace_sec');
        $this->assertNotNull($item);
        $this->assertSame(45, $item['value']);
        $this->assertSame('override', $item['source']);

        $this->assertDatabaseHas('automation_runtime_overrides', [
            'key' => 'automation_engine.scheduler_due_grace_sec',
            'value' => '45',
            'updated_by' => $admin->id,
        ]);

        $this->assertDatabaseHas('automation_runtime_overrides', [
            'key' => 'automation_engine.scheduler_catchup_policy',
            'value' => 'skip',
            'updated_by' => $admin->id,
        ]);

        $runtimeConfig = app(AutomationRuntimeConfigService::class);
        $schedulerConfig = $runtimeConfig->schedulerConfig();

        $this->assertSame(45, $schedulerConfig['due_grace_sec']);
        $this->assertSame('skip', $schedulerConfig['catchup_policy']);
    }

    public function test_agronomist_can_modify_runtime_settings(): void
    {
        Config::set('services.automation_engine.scheduler_due_grace_sec', 15);

        $agronomist = User::factory()->create(['role' => 'agronomist']);

        $response = $this->actingAs($agronomist)
            ->patchJson('/settings/automation-engine', [
                'settings' => [
                    'automation_engine.scheduler_due_grace_sec' => 41,
                ],
            ]);

        $response
            ->assertOk()
            ->assertJsonPath('status', 'ok');

        $item = $this->findSettingItem($response->json('data.sections'), 'automation_engine.scheduler_due_grace_sec');
        $this->assertNotNull($item);
        $this->assertSame(41, $item['value']);
        $this->assertSame('override', $item['source']);
    }

    public function test_settings_page_sets_can_edit_flag_for_agronomist(): void
    {
        $agronomist = User::factory()->create(['role' => 'agronomist']);

        $this->actingAs($agronomist)
            ->get('/settings')
            ->assertOk()
            ->assertInertia(function (AssertableInertia $page): void {
                $page
                    ->component('Settings/Index')
                    ->where('auth.user.role', 'agronomist')
                    ->where('canEditAutomationEngineSettings', true);
            });
    }

    public function test_admin_can_reset_runtime_overrides(): void
    {
        Config::set('services.automation_engine.scheduler_due_grace_sec', 15);

        $admin = User::factory()->create(['role' => 'admin']);
        AutomationRuntimeOverride::query()->create([
            'key' => 'automation_engine.scheduler_due_grace_sec',
            'value' => '50',
            'updated_by' => $admin->id,
        ]);

        $this->actingAs($admin)
            ->deleteJson('/settings/automation-engine')
            ->assertOk()
            ->assertJsonPath('status', 'ok');

        $this->assertDatabaseCount('automation_runtime_overrides', 0);

        $runtimeConfig = app(AutomationRuntimeConfigService::class);
        $schedulerConfig = $runtimeConfig->schedulerConfig();

        $this->assertSame(15, $schedulerConfig['due_grace_sec']);
    }

    public function test_scheduler_config_derives_hard_stale_from_expires_when_legacy_default_is_unchanged(): void
    {
        Config::set('services.automation_engine.scheduler_due_grace_sec', 15);
        Config::set('services.automation_engine.scheduler_expires_after_sec', 900);
        Config::set('services.automation_engine.scheduler_hard_stale_after_sec', 1200);

        $schedulerConfig = app(AutomationRuntimeConfigService::class)->schedulerConfig();

        $this->assertSame(900, $schedulerConfig['expires_after_sec']);
        $this->assertSame(1800, $schedulerConfig['hard_stale_after_sec']);
    }

    /**
     * @param  array<int, array<string, mixed>>|null  $sections
     * @return array<string, mixed>|null
     */
    private function findSettingItem(?array $sections, string $settingKey): ?array
    {
        if (! is_array($sections)) {
            return null;
        }

        foreach ($sections as $section) {
            $items = $section['items'] ?? null;
            if (! is_array($items)) {
                continue;
            }

            foreach ($items as $item) {
                if (($item['key'] ?? null) === $settingKey) {
                    return $item;
                }
            }
        }

        return null;
    }
}
