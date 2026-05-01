<?php

namespace Tests\Feature;

use App\Models\User;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\AutomationRuntimeConfigService;
use Inertia\Testing\AssertableInertia;
use Illuminate\Support\Facades\DB;
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

        $response = $this->actingAs($admin)->getJson('/api/automation-configs/system/0/system.runtime');

        $response
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonStructure([
                'status',
                'data' => [
                    'payload',
                    'snapshot' => [
                        'generated_at',
                        'sections' => [
                            '*' => [
                                'key',
                                'title',
                                'items',
                            ],
                        ],
                    ],
                ],
            ]);

        $item = $this->findSettingItem($response->json('data.snapshot.sections'), 'automation_engine.scheduler_due_grace_sec');
        $this->assertNotNull($item);
        $this->assertSame('default', $item['source']);
    }

    public function test_viewer_cannot_modify_runtime_settings(): void
    {
        $viewer = User::factory()->create(['role' => 'viewer']);

        $this->actingAs($viewer)
            ->putJson('/api/automation-configs/system/0/system.runtime', [
                'payload' => [
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
            ->putJson('/api/automation-configs/system/0/system.runtime', [
                'payload' => [
                    'automation_engine.scheduler_due_grace_sec' => 45,
                    'automation_engine.scheduler_catchup_policy' => 'skip',
                ],
            ]);

        $response->assertOk()->assertJsonPath('status', 'ok');

        $item = $this->findSettingItem($response->json('data.snapshot.sections'), 'automation_engine.scheduler_due_grace_sec');
        $this->assertNotNull($item);
        $this->assertSame(45, $item['value']);
        $this->assertSame('override', $item['source']);

        $payload = app(AutomationConfigDocumentService::class)->getPayload(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_RUNTIME,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            false
        );
        $this->assertSame(45, $payload['automation_engine.scheduler_due_grace_sec'] ?? null);
        $this->assertSame('skip', $payload['automation_engine.scheduler_catchup_policy'] ?? null);

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
            ->putJson('/api/automation-configs/system/0/system.runtime', [
                'payload' => [
                    'automation_engine.scheduler_due_grace_sec' => 41,
                ],
            ]);

        $response
            ->assertOk()
            ->assertJsonPath('status', 'ok');

        $item = $this->findSettingItem($response->json('data.snapshot.sections'), 'automation_engine.scheduler_due_grace_sec');
        $this->assertNotNull($item);
        $this->assertSame(41, $item['value']);
        $this->assertSame('override', $item['source']);
    }

    public function test_settings_page_no_longer_embeds_runtime_snapshot_props(): void
    {
        $agronomist = User::factory()->create(['role' => 'agronomist']);

        $this->actingAs($agronomist)
            ->get('/settings')
            ->assertOk()
            ->assertInertia(function (AssertableInertia $page): void {
                $page
                    ->component('Settings/Index')
                    ->where('auth.user.role', 'agronomist')
                    ->missing('automationEngineSettings')
                    ->missing('canEditAutomationEngineSettings');
            });
    }

    public function test_admin_can_reset_runtime_overrides(): void
    {
        Config::set('services.automation_engine.scheduler_due_grace_sec', 15);

        $admin = User::factory()->create(['role' => 'admin']);
        app(AutomationRuntimeConfigService::class)->applyOverrides([
            'automation_engine.scheduler_due_grace_sec' => 50,
        ], $admin->id);

        $this->actingAs($admin)
            ->deleteJson('/api/automation-configs/system/0/system.runtime')
            ->assertOk()
            ->assertJsonPath('status', 'ok');

        $payload = app(AutomationConfigDocumentService::class)->getPayload(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_RUNTIME,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            false
        );
        $this->assertSame(15, $payload['automation_engine.scheduler_due_grace_sec'] ?? null);

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

    public function test_scheduler_config_enforces_lock_ttl_from_p99_cycle_duration_plus_margin(): void
    {
        Config::set('services.automation_engine.scheduler_lock_ttl_sec', 30);
        Config::set('services.automation_engine.scheduler_lock_ttl_margin_sec', 10);

        DB::table('laravel_scheduler_cycle_duration_aggregates')->insert([
            'dispatch_mode' => 'start_cycle',
            'sample_count' => 100,
            'sample_sum' => 1200,
            'created_at' => now(),
            'updated_at' => now(),
        ]);
        DB::table('laravel_scheduler_cycle_duration_bucket_counts')->insert([
            'dispatch_mode' => 'start_cycle',
            'bucket_le' => '120',
            'sample_count' => 99,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $schedulerConfig = app(AutomationRuntimeConfigService::class)->schedulerConfig();

        $this->assertSame(130, $schedulerConfig['lock_ttl_sec']);
        $this->assertSame(10, $schedulerConfig['lock_ttl_margin_sec']);
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
