<?php

namespace Tests\Feature;

use App\Enums\GrowCycleStatus;
use App\Models\AutomationConfigDocument;
use App\Models\AutomationEffectiveBundle;
use App\Models\GrowStageTemplate;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\Zone;
use App\Services\AutomationConfigCompiler;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\AutomationRuntimeConfigService;
use App\Services\GrowCycle\GrowCycleAutomationDispatcher;
use App\Services\GrowCycleService;
use App\Services\ZoneService;
use Carbon\Carbon;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

class GrowCycleServiceTest extends TestCase
{
    use RefreshDatabase;

    private GrowCycleService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = app(GrowCycleService::class);
    }

    #[Test]
    public function it_creates_a_grow_cycle(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id);

        $this->assertDatabaseHas('grow_cycles', [
            'id' => $cycle->id,
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'plant_id' => $plant->id,
            'status' => GrowCycleStatus::PLANNED->value,
        ]);
        $this->assertNotNull($cycle->current_phase_id);
    }

    #[Test]
    public function it_materializes_first_phase_targets_from_revision_without_hidden_mutation(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        $phase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'ph_target' => 5.00,
            'ph_min' => 4.90,
            'ph_max' => 5.10,
            'ec_target' => 1.80,
            'ec_min' => 1.70,
            'ec_max' => 1.90,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id);

        $firstPhase = $cycle->phases()->orderBy('phase_index')->firstOrFail();

        $this->assertSame((float) $phase->ph_target, (float) $firstPhase->ph_target);
        $this->assertSame((float) $phase->ph_min, (float) $firstPhase->ph_min);
        $this->assertSame((float) $phase->ph_max, (float) $firstPhase->ph_max);
        $this->assertSame((float) $phase->ec_target, (float) $firstPhase->ec_target);
        $this->assertSame((float) $phase->ec_min, (float) $firstPhase->ec_min);
        $this->assertSame((float) $phase->ec_max, (float) $firstPhase->ec_max);
    }

    #[Test]
    public function it_syncs_empty_phase_override_document(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'ph_target' => 5.00,
            'ph_min' => 4.90,
            'ph_max' => 5.10,
            'ec_target' => 1.80,
            'ec_min' => 1.70,
            'ec_max' => 1.90,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id);

        $this->service->syncCycleConfigDocuments($cycle, [
            'phase_overrides' => [
                'ph_target' => 5.80,
            ],
        ]);

        $document = AutomationConfigDocument::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_GROW_CYCLE)
            ->where('scope_id', $cycle->id)
            ->where('namespace', AutomationConfigRegistry::NAMESPACE_CYCLE_PHASE_OVERRIDES)
            ->first();

        $this->assertNotNull($document);
        $this->assertSame([], $document->payload);
    }

    #[Test]
    public function it_starts_a_cycle(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id);
        $plantingAt = Carbon::now();

        $startedCycle = $this->service->startCycle($cycle, $plantingAt);

        $this->assertEquals(GrowCycleStatus::RUNNING, $startedCycle->status);
        $this->assertNotNull($startedCycle->planting_at);
        $this->assertSame('RUNNING', $zone->fresh()->status);
    }

    #[Test]
    public function it_computes_expected_harvest(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'duration_hours' => 24,
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 1,
            'duration_hours' => 24 * 30,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id);
        $plantingAt = Carbon::now();
        $startedCycle = $this->service->startCycle($cycle, $plantingAt);

        $this->assertNotNull($startedCycle->expected_harvest_at);
        $expectedHarvest = Carbon::parse($startedCycle->expected_harvest_at);
        $this->assertEquals(31, $plantingAt->diffInDays($expectedHarvest));
    }

    #[Test]
    public function it_advances_stage_automatically(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();

        $template1 = GrowStageTemplate::factory()->create([
            'code' => 'PLANTING',
            'order_index' => 0,
        ]);
        $template2 = GrowStageTemplate::factory()->create([
            'code' => 'VEG',
            'order_index' => 1,
        ]);

        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'stage_template_id' => $template1->id,
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 1,
            'stage_template_id' => $template2->id,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id);
        $cycle = $this->service->startCycle($cycle);
        $cycle->update(['current_stage_code' => 'PLANTING']);

        $advancedCycle = $this->service->advanceStage($cycle);

        $this->assertEquals('VEG', $advancedCycle->current_stage_code);
    }

    #[Test]
    public function it_advances_to_specific_stage(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();

        $template1 = GrowStageTemplate::factory()->create(['code' => 'PLANTING', 'order_index' => 0]);
        $template2 = GrowStageTemplate::factory()->create(['code' => 'VEG', 'order_index' => 1]);
        $template3 = GrowStageTemplate::factory()->create(['code' => 'FLOWER', 'order_index' => 2]);

        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'stage_template_id' => $template1->id,
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 1,
            'stage_template_id' => $template2->id,
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 2,
            'stage_template_id' => $template3->id,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id);
        $cycle = $this->service->startCycle($cycle);
        $cycle->update(['current_stage_code' => 'PLANTING']);

        $advancedCycle = $this->service->advanceStage($cycle, 'FLOWER');

        $this->assertEquals('FLOWER', $advancedCycle->current_stage_code);
    }

    #[Test]
    public function it_stores_grow_cycle_start_intent_as_wakeup_only_payload(): void
    {
        $zone = Zone::factory()->create();
        $cycleId = 345;
        $idempotencyKey = sprintf('gcs:z%d:c%d:test', $zone->id, $cycleId);

        $dispatcher = app(GrowCycleAutomationDispatcher::class);
        $method = new \ReflectionMethod($dispatcher, 'upsertStartIntent');
        $method->setAccessible(true);
        $method->invoke($dispatcher, $zone->id, $cycleId, $idempotencyKey);

        $intentRow = DB::table('zone_automation_intents')
            ->where('idempotency_key', $idempotencyKey)
            ->first();

        $this->assertNotNull($intentRow);
        $this->assertNull($intentRow->payload);
        $this->assertSame('laravel_grow_cycle_start', $intentRow->intent_source);
        $this->assertSame('cycle_start', $intentRow->task_type);
        $this->assertSame('two_tank_drip_substrate_trays', $intentRow->topology);
        $this->assertSame('DIAGNOSTICS_TICK', $intentRow->intent_type);

        $this->assertDatabaseHas('automation_config_documents', [
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            'scope_type' => AutomationConfigRegistry::SCOPE_ZONE,
            'scope_id' => $zone->id,
        ]);
        $this->assertDatabaseHas('automation_config_versions', [
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            'scope_type' => AutomationConfigRegistry::SCOPE_ZONE,
            'scope_id' => $zone->id,
            'source' => 'bootstrap',
        ]);
    }

    #[Test]
    public function it_treats_empty_cycle_start_snapshot_placeholder_as_valid_bundle_state(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id);
        $documents = app(AutomationConfigDocumentService::class);
        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_CYCLE_START_SNAPSHOT,
            AutomationConfigRegistry::SCOPE_GROW_CYCLE,
            (int) $cycle->id,
            [],
            null,
            'test'
        );

        $bundle = app(AutomationConfigCompiler::class)->compileGrowCycleBundle((int) $cycle->id);

        $this->assertSame('valid', $bundle->status);
        $this->assertSame([], $bundle->violations);
    }

    #[Test]
    public function it_dispatches_cycle_start_only_after_cycle_documents_and_bundle_revision_are_persisted(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        $phase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);

        $runtimeConfig = $this->createMock(AutomationRuntimeConfigService::class);
        $runtimeConfig->method('schedulerConfig')->willReturn([
            'api_url' => 'http://automation-engine:9405',
            'timeout_sec' => 2.0,
            'scheduler_id' => 'laravel-scheduler',
            'token' => 'test-token',
        ]);

        $dispatcher = new class($runtimeConfig, app(AutomationConfigDocumentService::class)) extends GrowCycleAutomationDispatcher {
            /** @var array<string, mixed> */
            public array $dispatchState = [];

            protected function isEnabled(): bool
            {
                return true;
            }

            protected function shouldDispatchForZone(int $zoneId): bool
            {
                return true;
            }

            protected function postStartCycle(int $zoneId, string $idempotencyKey, array $cfg): array
            {
                preg_match('/^gcs:z(?P<zone>\d+):c(?P<cycle>\d+):/', $idempotencyKey, $matches);
                $cycleId = (int) ($matches['cycle'] ?? 0);

                $cycle = \App\Models\GrowCycle::query()->findOrFail($cycleId);
                $startSnapshot = \App\Models\AutomationConfigDocument::query()
                    ->where('namespace', AutomationConfigRegistry::NAMESPACE_CYCLE_START_SNAPSHOT)
                    ->where('scope_type', AutomationConfigRegistry::SCOPE_GROW_CYCLE)
                    ->where('scope_id', $cycleId)
                    ->first();
                $bundle = \App\Models\AutomationEffectiveBundle::query()
                    ->where('scope_type', AutomationConfigRegistry::SCOPE_GROW_CYCLE)
                    ->where('scope_id', $cycleId)
                    ->first();

                $this->dispatchState = [
                    'zone_id' => $zoneId,
                    'cycle_id' => $cycleId,
                    'idempotency_key' => $idempotencyKey,
                    'cycle_status' => $cycle->status instanceof GrowCycleStatus ? $cycle->status->value : $cycle->status,
                    'cycle_settings_bundle_revision' => data_get($cycle->settings, 'bundle_revision'),
                    'start_snapshot_exists' => $startSnapshot !== null,
                    'start_snapshot_phase_id' => data_get($startSnapshot?->payload, 'phase.phase_id'),
                    'bundle_exists' => $bundle !== null,
                    'bundle_revision' => $bundle?->bundle_revision,
                    'bundle_phase_id' => data_get($bundle?->config, 'cycle.start_snapshot.phase.phase_id'),
                ];

                return [
                    'data' => [
                        'accepted' => true,
                        'deduplicated' => false,
                        'task_id' => 'ae3-task-1',
                    ],
                ];
            }
        };

        $this->app->instance(GrowCycleAutomationDispatcher::class, $dispatcher);
        $service = app(GrowCycleService::class);

        $cycle = $service->createCycle($zone, $revision, $plant->id, [
            'start_immediately' => false,
        ]);
        $phaseSnapshot = $cycle->phases()->orderBy('phase_index')->firstOrFail();
        $documents = app(AutomationConfigDocumentService::class);
        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_CYCLE_START_SNAPSHOT,
            AutomationConfigRegistry::SCOPE_GROW_CYCLE,
            (int) $cycle->id,
            [
                'cycle_id' => (int) $cycle->id,
                'zone_id' => (int) $cycle->zone_id,
                'recipe_revision_id' => (int) $cycle->recipe_revision_id,
                'phase' => [
                    'phase_id' => (int) $phaseSnapshot->recipe_revision_phase_id,
                    'phase_index' => (int) $phaseSnapshot->phase_index,
                    'name' => $phaseSnapshot->name,
                    'ph_target' => $phaseSnapshot->ph_target,
                    'ph_min' => $phaseSnapshot->ph_min,
                    'ph_max' => $phaseSnapshot->ph_max,
                    'ec_target' => $phaseSnapshot->ec_target,
                    'ec_min' => $phaseSnapshot->ec_min,
                    'ec_max' => $phaseSnapshot->ec_max,
                    'irrigation_mode' => $phaseSnapshot->irrigation_mode,
                    'irrigation_interval_sec' => $phaseSnapshot->irrigation_interval_sec,
                    'irrigation_duration_sec' => $phaseSnapshot->irrigation_duration_sec,
                    'extensions' => is_array($phaseSnapshot->extensions) ? $phaseSnapshot->extensions : [],
                ],
            ]
        );
        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_CYCLE_PHASE_OVERRIDES,
            AutomationConfigRegistry::SCOPE_GROW_CYCLE,
            (int) $cycle->id,
            [
                'ph_target' => 6.0,
                'ec_target' => 1.5,
            ]
        );

        $startedCycle = $service->startCycle($cycle->fresh(), Carbon::now());

        $this->assertSame(GrowCycleStatus::RUNNING, $startedCycle->status);
        $this->assertTrue($dispatcher->dispatchState['start_snapshot_exists']);
        $this->assertTrue($dispatcher->dispatchState['bundle_exists']);
        $this->assertSame('RUNNING', $dispatcher->dispatchState['cycle_status']);
        $this->assertNotSame('', (string) $dispatcher->dispatchState['bundle_revision']);
        $this->assertSame($phase->id, $dispatcher->dispatchState['start_snapshot_phase_id']);
        $this->assertSame($phase->id, $dispatcher->dispatchState['bundle_phase_id']);
        $this->assertSame(
            $dispatcher->dispatchState['bundle_revision'],
            $dispatcher->dispatchState['cycle_settings_bundle_revision']
        );
    }

    #[Test]
    public function it_does_not_throw_after_commit_when_automation_start_cycle_dispatch_fails(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);

        $runtimeConfig = $this->createMock(AutomationRuntimeConfigService::class);
        $dispatcher = new class($runtimeConfig, app(AutomationConfigDocumentService::class)) extends GrowCycleAutomationDispatcher {
            public int $dispatchAttempts = 0;

            protected function isEnabled(): bool
            {
                return true;
            }

            protected function shouldDispatchForZone(int $zoneId): bool
            {
                return true;
            }

            protected function automationStartCycleConfig(): array
            {
                return [
                    'api_url' => 'http://automation-engine:9405',
                    'timeout_sec' => 2.0,
                    'scheduler_id' => 'laravel-scheduler',
                    'token' => 'test-token',
                ];
            }

            protected function postStartCycle(int $zoneId, string $idempotencyKey, array $cfg): array
            {
                $this->dispatchAttempts++;

                throw new \RuntimeException('automation_engine_start_cycle_http_error_v2:500:boom');
            }
        };

        $this->app->instance(GrowCycleAutomationDispatcher::class, $dispatcher);
        $service = app(GrowCycleService::class);

        $cycle = $service->createCycle($zone, $revision, $plant->id);
        $startedCycle = $service->startCycle($cycle, Carbon::now());

        $this->assertSame(1, $dispatcher->dispatchAttempts);
        $this->assertSame(GrowCycleStatus::RUNNING, $startedCycle->status);
        $this->assertSame('RUNNING', $zone->fresh()->status);
        $this->assertDatabaseHas('grow_cycles', [
            'id' => $cycle->id,
            'status' => GrowCycleStatus::RUNNING->value,
        ]);
        $this->assertDatabaseHas('zone_automation_intents', [
            'zone_id' => $zone->id,
            'status' => 'failed',
            'error_code' => 'automation_engine_start_cycle_http_error',
        ]);
    }

    #[Test]
    public function it_retries_zone_not_found_before_marking_start_cycle_dispatch_as_failed(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);

        $runtimeConfig = $this->createMock(AutomationRuntimeConfigService::class);
        $dispatcher = new class($runtimeConfig, app(AutomationConfigDocumentService::class)) extends GrowCycleAutomationDispatcher {
            public int $dispatchAttempts = 0;

            protected function isEnabled(): bool
            {
                return true;
            }

            protected function shouldDispatchForZone(int $zoneId): bool
            {
                return true;
            }

            protected function automationStartCycleConfig(): array
            {
                return [
                    'api_url' => 'http://automation-engine:9405',
                    'timeout_sec' => 2.0,
                    'scheduler_id' => 'laravel-scheduler',
                    'token' => 'test-token',
                ];
            }

            protected function retryDelayMs(int $attempt): int
            {
                return 1;
            }

            protected function postStartCycle(int $zoneId, string $idempotencyKey, array $cfg): array
            {
                $this->dispatchAttempts++;

                if ($this->dispatchAttempts < 3) {
                    throw new \RuntimeException(sprintf(
                        'automation_engine_start_cycle_http_error_v2:404:{"detail":"Zone \'%d\' not found"}',
                        $zoneId
                    ));
                }

                return [
                    'data' => [
                        'accepted' => true,
                        'deduplicated' => false,
                        'task_id' => 'ae3-task-retry-ok',
                    ],
                ];
            }
        };

        $this->app->instance(GrowCycleAutomationDispatcher::class, $dispatcher);
        $service = app(GrowCycleService::class);

        $cycle = $service->createCycle($zone, $revision, $plant->id);
        $startedCycle = $service->startCycle($cycle, Carbon::now());

        $this->assertSame(3, $dispatcher->dispatchAttempts);
        $this->assertSame(GrowCycleStatus::RUNNING, $startedCycle->status);
        $this->assertDatabaseHas('zone_automation_intents', [
            'zone_id' => $zone->id,
            'status' => 'pending',
        ]);
    }

    #[Test]
    public function it_retries_start_cycle_zone_busy_and_marks_intent_failed_with_structured_code(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);

        $runtimeConfig = $this->createMock(AutomationRuntimeConfigService::class);
        $dispatcher = new class($runtimeConfig, app(AutomationConfigDocumentService::class)) extends GrowCycleAutomationDispatcher {
            public int $dispatchAttempts = 0;

            protected function isEnabled(): bool
            {
                return true;
            }

            protected function shouldDispatchForZone(int $zoneId): bool
            {
                return true;
            }

            protected function automationStartCycleConfig(): array
            {
                return [
                    'api_url' => 'http://automation-engine:9405',
                    'timeout_sec' => 2.0,
                    'scheduler_id' => 'laravel-scheduler',
                    'token' => 'test-token',
                ];
            }

            protected function retryDelayMs(int $attempt): int
            {
                return 1;
            }

            protected function postStartCycle(int $zoneId, string $idempotencyKey, array $cfg): array
            {
                $this->dispatchAttempts++;

                throw new \RuntimeException(
                    'automation_engine_start_cycle_http_error_v2:409:{"detail":{"error":"start_cycle_zone_busy","zone_id":'
                    .$zoneId.',"active_task_id":42}}'
                );
            }
        };

        $this->app->instance(GrowCycleAutomationDispatcher::class, $dispatcher);
        $service = app(GrowCycleService::class);

        $cycle = $service->createCycle($zone, $revision, $plant->id);
        $startedCycle = $service->startCycle($cycle, Carbon::now());

        $this->assertSame(5, $dispatcher->dispatchAttempts);
        $this->assertSame(GrowCycleStatus::RUNNING, $startedCycle->status);
        $this->assertDatabaseHas('zone_automation_intents', [
            'zone_id' => $zone->id,
            'status' => 'failed',
            'error_code' => 'automation_engine_start_cycle_zone_busy',
        ]);
    }

    #[Test]
    public function automation_dispatcher_enabled_flag_works_in_console_runtime(): void
    {
        $runtimeConfig = $this->createMock(AutomationRuntimeConfigService::class);
        $runtimeConfig
            ->expects($this->once())
            ->method('automationEngineValue')
            ->with('grow_cycle_start_dispatch_enabled', false)
            ->willReturn(true);

        $dispatcher = new class($runtimeConfig, app(AutomationConfigDocumentService::class)) extends GrowCycleAutomationDispatcher {
            public function enabledForTest(): bool
            {
                return $this->isEnabled();
            }
        };

        $this->assertTrue($dispatcher->enabledForTest());
    }

    #[Test]
    public function it_skips_automation_start_cycle_dispatch_when_zone_two_tank_topology_is_incomplete(): void
    {
        $zone = Zone::factory()->create([
            'automation_runtime' => 'ae3',
        ]);
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);

        $runtimeConfig = $this->createMock(AutomationRuntimeConfigService::class);
        $dispatcher = new class($runtimeConfig, app(AutomationConfigDocumentService::class)) extends GrowCycleAutomationDispatcher {
            public int $dispatchAttempts = 0;

            protected function isEnabled(): bool
            {
                return true;
            }

            protected function postStartCycle(int $zoneId, string $idempotencyKey, array $cfg): array
            {
                $this->dispatchAttempts++;

                return [
                    'data' => [
                        'accepted' => true,
                        'deduplicated' => false,
                        'task_id' => 'should-not-run',
                    ],
                ];
            }
        };

        $this->app->instance(GrowCycleAutomationDispatcher::class, $dispatcher);
        $service = app(GrowCycleService::class);

        $cycle = $service->createCycle($zone, $revision, $plant->id);
        $startedCycle = $service->startCycle($cycle, Carbon::now());

        $this->assertSame(0, $dispatcher->dispatchAttempts);
        $this->assertSame(GrowCycleStatus::RUNNING, $startedCycle->status);
        $this->assertDatabaseMissing('zone_automation_intents', [
            'zone_id' => $zone->id,
            'intent_type' => 'DIAGNOSTICS_TICK',
        ]);
    }

    #[Test]
    public function it_cancels_related_ae3_start_cycle_runtime_state_when_cycle_is_aborted(): void
    {
        $zone = Zone::factory()->create([
            'automation_runtime' => 'ae3',
        ]);
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id, [
            'start_immediately' => false,
        ]);
        $idempotencyKey = sprintf(
            'gcs:z%d:c%d:%s',
            $zone->id,
            $cycle->id,
            substr(hash('sha256', sprintf('grow-cycle-start|zone:%d|cycle:%d', $zone->id, $cycle->id)), 0, 24)
        );
        $schedulerKey = sprintf('e93-start-cycle-%d', $cycle->id);
        $now = Carbon::now('UTC')->setMicroseconds(0);

        DB::table('zone_automation_intents')->insert([
            [
                'zone_id' => $zone->id,
                'intent_type' => 'DIAGNOSTICS_TICK',
                'payload' => json_encode([
                    'source' => 'laravel_grow_cycle_start',
                    'task_type' => 'diagnostics',
                    'workflow' => 'cycle_start',
                    'topology' => 'two_tank_drip_substrate_trays',
                    'grow_cycle_id' => $cycle->id,
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'idempotency_key' => $idempotencyKey,
                'status' => 'pending',
                'not_before' => $now,
                'retry_count' => 0,
                'max_retries' => 3,
                'created_at' => $now,
                'updated_at' => $now,
            ],
            [
                'zone_id' => $zone->id,
                'intent_type' => 'DIAGNOSTICS_TICK',
                'payload' => json_encode([
                    'source' => 'laravel_scheduler',
                    'task_type' => 'diagnostics',
                    'workflow' => 'cycle_start',
                    'topology' => 'two_tank_drip_substrate_trays',
                    'grow_cycle_id' => $cycle->id,
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'idempotency_key' => $schedulerKey,
                'status' => 'running',
                'not_before' => $now,
                'retry_count' => 0,
                'max_retries' => 3,
                'created_at' => $now,
                'updated_at' => $now,
            ],
        ]);

        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'running',
            'idempotency_key' => $schedulerKey,
            'topology' => 'two_tank_drip_substrate_trays',
            'current_stage' => 'solution_fill_start',
            'workflow_phase' => 'tank_filling',
            'control_mode_snapshot' => 'auto',
            'intent_source' => 'laravel_scheduler',
            'intent_trigger' => 'irrigate_once',
            'intent_meta' => json_encode([
                'intent_payload' => [
                    'workflow' => 'cycle_start',
                    'grow_cycle_id' => $cycle->id,
                ],
            ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'scheduled_for' => $now,
            'due_at' => $now,
            'stage_entered_at' => $now,
            'created_at' => $now,
            'updated_at' => $now,
        ]);

        DB::table('ae_zone_leases')->insert([
            'zone_id' => $zone->id,
            'owner' => 'worker:test',
            'leased_until' => $now->copy()->addMinute(),
            'updated_at' => $now,
        ]);

        $aborted = $this->service->abort($cycle->fresh(), ['notes' => 'test abort'], 7);

        $this->assertSame(GrowCycleStatus::ABORTED, $aborted->status);
        $this->assertDatabaseHas('zone_automation_intents', [
            'zone_id' => $zone->id,
            'idempotency_key' => $idempotencyKey,
            'status' => 'cancelled',
            'error_code' => 'grow_cycle_aborted',
        ]);
        $this->assertDatabaseHas('zone_automation_intents', [
            'zone_id' => $zone->id,
            'idempotency_key' => $schedulerKey,
            'status' => 'cancelled',
            'error_code' => 'grow_cycle_aborted',
        ]);
        $this->assertDatabaseHas('ae_tasks', [
            'zone_id' => $zone->id,
            'idempotency_key' => $schedulerKey,
            'status' => 'cancelled',
            'error_code' => 'grow_cycle_aborted',
        ]);
        $this->assertDatabaseHas('ae_zone_leases', [
            'zone_id' => $zone->id,
        ]);
    }

    #[Test]
    public function it_cancels_active_ae3_start_cycle_runtime_state_on_harvest(): void
    {
        config()->set('services.automation_engine.grow_cycle_start_dispatch_enabled', true);

        $zone = Zone::factory()->create(['automation_runtime' => 'ae3']);
        $recipe = Recipe::factory()->create();
        $plant = Plant::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id, [
            'start_immediately' => false,
        ]);
        $idempotencyKey = sprintf(
            'gcs:z%d:c%d:%s',
            $zone->id,
            $cycle->id,
            substr(hash('sha256', sprintf('grow-cycle-start|zone:%d|cycle:%d', $zone->id, $cycle->id)), 0, 24)
        );
        $schedulerKey = sprintf('harvest-start-cycle-%d', $cycle->id);
        $now = Carbon::now('UTC')->setMicroseconds(0);

        DB::table('zone_automation_intents')->insert([
            [
                'zone_id' => $zone->id,
                'intent_type' => 'DIAGNOSTICS_TICK',
                'payload' => json_encode([
                    'source' => 'laravel_grow_cycle_start',
                    'task_type' => 'diagnostics',
                    'workflow' => 'cycle_start',
                    'topology' => 'two_tank_drip_substrate_trays',
                    'grow_cycle_id' => $cycle->id,
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'idempotency_key' => $idempotencyKey,
                'status' => 'pending',
                'not_before' => $now,
                'retry_count' => 0,
                'max_retries' => 3,
                'created_at' => $now,
                'updated_at' => $now,
            ],
            [
                'zone_id' => $zone->id,
                'intent_type' => 'DIAGNOSTICS_TICK',
                'payload' => json_encode([
                    'source' => 'laravel_scheduler',
                    'task_type' => 'diagnostics',
                    'workflow' => 'cycle_start',
                    'topology' => 'two_tank_drip_substrate_trays',
                    'grow_cycle_id' => $cycle->id,
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'idempotency_key' => $schedulerKey,
                'status' => 'running',
                'not_before' => $now,
                'retry_count' => 0,
                'max_retries' => 3,
                'created_at' => $now,
                'updated_at' => $now,
            ],
        ]);

        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'running',
            'idempotency_key' => $schedulerKey,
            'topology' => 'two_tank_drip_substrate_trays',
            'current_stage' => 'solution_fill_start',
            'workflow_phase' => 'tank_filling',
            'control_mode_snapshot' => 'auto',
            'intent_source' => 'laravel_scheduler',
            'intent_trigger' => 'irrigate_once',
            'intent_meta' => json_encode([
                'intent_payload' => [
                    'workflow' => 'cycle_start',
                    'grow_cycle_id' => $cycle->id,
                ],
            ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'scheduled_for' => $now,
            'due_at' => $now,
            'stage_entered_at' => $now,
            'created_at' => $now,
            'updated_at' => $now,
        ]);

        DB::table('ae_zone_leases')->insert([
            'zone_id' => $zone->id,
            'owner' => 'worker:test',
            'leased_until' => $now->copy()->addMinute(),
            'updated_at' => $now,
        ]);

        $harvested = $this->service->harvest($cycle->fresh(), ['batch_label' => 'batch-1'], 7);

        $this->assertSame(GrowCycleStatus::HARVESTED, $harvested->status);
        $this->assertDatabaseHas('zone_automation_intents', [
            'zone_id' => $zone->id,
            'idempotency_key' => $idempotencyKey,
            'status' => 'cancelled',
            'error_code' => 'grow_cycle_harvested',
        ]);
        $this->assertDatabaseHas('zone_automation_intents', [
            'zone_id' => $zone->id,
            'idempotency_key' => $schedulerKey,
            'status' => 'cancelled',
            'error_code' => 'grow_cycle_harvested',
        ]);
        $this->assertDatabaseHas('ae_tasks', [
            'zone_id' => $zone->id,
            'idempotency_key' => $schedulerKey,
            'status' => 'cancelled',
            'error_code' => 'grow_cycle_harvested',
        ]);
        $this->assertDatabaseHas('ae_zone_leases', [
            'zone_id' => $zone->id,
        ]);
    }

    #[Test]
    public function it_preserves_snapshot_immutability_when_changing_revision_with_next_phase_mode(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $oldRevision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'revision_number' => 1,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $oldRevision->id,
            'phase_index' => 0,
            'name' => 'Old Phase',
            'ph_target' => 5.80,
            'ec_target' => 1.40,
        ]);

        $newRevision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'revision_number' => 2,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $newRevision->id,
            'phase_index' => 0,
            'name' => 'New Phase',
            'ph_target' => 6.20,
            'ec_target' => 2.00,
        ]);

        $cycle = $this->service->createCycle($zone, $oldRevision, $plant->id);
        $originalPhaseId = $cycle->current_phase_id;
        $originalSnapshotPhTarget = (float) $cycle->currentPhase->ph_target;
        $this->assertSame(5.80, $originalSnapshotPhTarget);

        $user = \App\Models\User::factory()->create(['role' => 'agronomist']);
        $updated = $this->service->changeRecipeRevision($cycle->fresh(), $newRevision, 'next_phase', $user->id);

        // recipe_revision_id обновился
        $this->assertSame($newRevision->id, $updated->recipe_revision_id);
        // current_phase_id не меняется в next_phase режиме
        $this->assertSame($originalPhaseId, $updated->current_phase_id);
        // snapshot фазы не изменился — targets остались от старой ревизии
        $this->assertSame(5.80, (float) $updated->currentPhase->ph_target);
        $this->assertSame(1.40, (float) $updated->currentPhase->ec_target);
    }

    #[Test]
    public function it_creates_new_snapshot_immediately_when_changing_revision_with_now_mode(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $oldRevision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'revision_number' => 1,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $oldRevision->id,
            'phase_index' => 0,
            'ph_target' => 5.80,
            'ec_target' => 1.40,
        ]);

        $newRevision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'revision_number' => 2,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $newRevision->id,
            'phase_index' => 0,
            'ph_target' => 6.20,
            'ec_target' => 2.00,
        ]);

        $cycle = $this->service->createCycle($zone, $oldRevision, $plant->id);
        $originalPhaseId = $cycle->current_phase_id;

        $user = \App\Models\User::factory()->create(['role' => 'agronomist']);
        $updated = $this->service->changeRecipeRevision($cycle->fresh(), $newRevision, 'now', $user->id);

        // current_phase_id сменился на новый snapshot
        $this->assertNotSame($originalPhaseId, $updated->current_phase_id);
        // snapshot содержит targets новой ревизии
        $this->assertSame(6.20, (float) $updated->currentPhase->ph_target);
        $this->assertSame(2.00, (float) $updated->currentPhase->ec_target);
        // Для разрешения UNIQUE (grow_cycle_id, phase_index) новому snapshot
        // назначен max+1 (в цикле уже был snapshot с phase_index=0).
        $this->assertSame(1, (int) $updated->currentPhase->phase_index);
        // Исторический snapshot старой ревизии сохранён (не удалён).
        $this->assertDatabaseHas('grow_cycle_phases', [
            'id' => $originalPhaseId,
            'phase_index' => 0,
        ]);
    }

    #[Test]
    public function it_cancels_active_ae_tasks_and_intents_on_harvest(): void
    {
        $zone = Zone::factory()->create(['automation_runtime' => 'ae3']);
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);
        $cycle = $this->service->createCycle($zone, $revision, $plant->id);

        // Эмулируем активный irrigation intent + ae_task (не cycle-start).
        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id,
            'intent_type' => 'IRRIGATE_ONCE',
            'task_type' => 'irrigation',
            'status' => 'running',
            'idempotency_key' => 'test-irr-intent-1',
            'payload' => json_encode(['source' => 'scheduler']),
            'not_before' => now(),
            'created_at' => now(),
            'updated_at' => now(),
        ]);
        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'irrigation_start',
            'status' => 'running',
            'idempotency_key' => 'test-irr-task-1',
            'scheduled_for' => now(),
            'due_at' => now(),
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $user = \App\Models\User::factory()->create(['role' => 'agronomist']);
        $this->service->harvest($cycle->fresh(), [], $user->id);

        $this->assertDatabaseHas('zone_automation_intents', [
            'idempotency_key' => 'test-irr-intent-1',
            'status' => 'cancelled',
            'error_code' => 'grow_cycle_harvested',
        ]);
        $this->assertDatabaseHas('ae_tasks', [
            'idempotency_key' => 'test-irr-task-1',
            'status' => 'cancelled',
            'error_code' => 'grow_cycle_harvested',
        ]);
    }

    #[Test]
    public function it_emits_cycle_started_event_on_start_cycle(): void
    {
        $zone = Zone::factory()->create(['status' => 'NEW']);
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);
        $cycle = $this->service->createCycle($zone, $revision, $plant->id);
        $this->service->startCycle($cycle->fresh());

        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'CYCLE_STARTED',
            'entity_type' => 'grow_cycle',
            'entity_id' => (string) $cycle->id,
        ]);
    }

    #[Test]
    public function ae3_reap_stale_tasks_marks_expired_tasks_as_failed(): void
    {
        $zoneA = Zone::factory()->create();
        $zoneB = Zone::factory()->create();
        DB::table('ae_tasks')->insert([
            'zone_id' => $zoneA->id,
            'task_type' => 'irrigation_start',
            'status' => 'running',
            'idempotency_key' => 'reap-test-deadline',
            'scheduled_for' => now(),
            'due_at' => now(),
            'stage_deadline_at' => now()->subMinutes(5),
            'created_at' => now()->subMinutes(10),
            'updated_at' => now()->subMinutes(5),
        ]);
        DB::table('ae_tasks')->insert([
            'zone_id' => $zoneB->id,
            'task_type' => 'cycle_start',
            'status' => 'claimed',
            'idempotency_key' => 'reap-test-claim-stale',
            'scheduled_for' => now(),
            'due_at' => now(),
            'claimed_at' => now()->subMinutes(10),
            'created_at' => now()->subMinutes(10),
            'updated_at' => now()->subMinutes(10),
        ]);

        $this->artisan('ae3:reap-stale-tasks', ['--claim-stale-after' => 60])
            ->assertSuccessful();

        $this->assertDatabaseHas('ae_tasks', [
            'idempotency_key' => 'reap-test-deadline',
            'status' => 'failed',
            'error_code' => 'stage_deadline_exceeded',
        ]);
        $this->assertDatabaseHas('ae_tasks', [
            'idempotency_key' => 'reap-test-claim-stale',
            'status' => 'failed',
            'error_code' => 'claim_stale',
        ]);
    }

    #[Test]
    public function ae3_cleanup_old_tasks_deletes_only_old_terminal_records(): void
    {
        $zone = Zone::factory()->create();
        // Старая completed — должна быть удалена
        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'completed',
            'idempotency_key' => 'cleanup-old',
            'scheduled_for' => now()->subDays(120),
            'due_at' => now()->subDays(120),
            'created_at' => now()->subDays(120),
            'updated_at' => now()->subDays(120),
        ]);
        // Свежая completed — остаётся
        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'completed',
            'idempotency_key' => 'cleanup-fresh',
            'scheduled_for' => now()->subDays(10),
            'due_at' => now()->subDays(10),
            'created_at' => now()->subDays(10),
            'updated_at' => now()->subDays(10),
        ]);
        // Старая running — остаётся (не terminal)
        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'irrigation_start',
            'status' => 'running',
            'idempotency_key' => 'cleanup-running-old',
            'scheduled_for' => now()->subDays(200),
            'due_at' => now()->subDays(200),
            'created_at' => now()->subDays(200),
            'updated_at' => now()->subDays(200),
        ]);

        $this->artisan('ae3:cleanup-old-tasks', ['--days' => 90])
            ->assertSuccessful();

        $this->assertDatabaseMissing('ae_tasks', ['idempotency_key' => 'cleanup-old']);
        $this->assertDatabaseHas('ae_tasks', ['idempotency_key' => 'cleanup-fresh']);
        $this->assertDatabaseHas('ae_tasks', ['idempotency_key' => 'cleanup-running-old']);
    }

    #[Test]
    public function cycle_events_include_correlation_id_from_trace_header(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);

        request()->headers->set('X-Trace-Id', 'trace-abc-123');
        $cycle = $this->service->createCycle($zone, $revision, $plant->id);

        $event = DB::table('zone_events')
            ->where('zone_id', $zone->id)
            ->where('type', 'CYCLE_CREATED')
            ->first();
        $this->assertNotNull($event);
        $payload = json_decode($event->payload_json, true);
        $this->assertSame('trace-abc-123', $payload['correlation_id'] ?? null);
    }

    #[Test]
    public function it_cancels_pending_scheduler_intents_on_phase_advance(): void
    {
        $zone = Zone::factory()->create(['automation_runtime' => 'ae3']);
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 1,
        ]);
        $cycle = $this->service->createCycle($zone, $revision, $plant->id);

        // Stale IRRIGATE_ONCE из предыдущей фазы, ещё не диспатчен.
        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id,
            'intent_type' => 'IRRIGATE_ONCE',
            'task_type' => 'irrigation',
            'status' => 'pending',
            'idempotency_key' => 'test-stale-intent',
            'payload' => json_encode(['source' => 'scheduler']),
            'not_before' => now(),
            'created_at' => now(),
            'updated_at' => now(),
        ]);
        // Running intent не должен быть тронут — AE3 его активно исполняет.
        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id,
            'intent_type' => 'IRRIGATE_ONCE',
            'task_type' => 'irrigation',
            'status' => 'running',
            'idempotency_key' => 'test-running-intent',
            'payload' => json_encode(['source' => 'scheduler']),
            'not_before' => now(),
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $user = \App\Models\User::factory()->create(['role' => 'agronomist']);
        $this->service->advancePhase($cycle->fresh(), $user->id);

        $this->assertDatabaseHas('zone_automation_intents', [
            'idempotency_key' => 'test-stale-intent',
            'status' => 'cancelled',
            'error_code' => 'phase_advanced_before_dispatch',
        ]);
        $this->assertDatabaseHas('zone_automation_intents', [
            'idempotency_key' => 'test-running-intent',
            'status' => 'running',
        ]);
    }
}
