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
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\AutomationRuntimeConfigService;
use App\Services\GrowCycleService;
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

        $method = new \ReflectionMethod($this->service, 'upsertGrowCycleStartIntent');
        $method->setAccessible(true);
        $method->invoke($this->service, $zone->id, $cycleId, $idempotencyKey);

        $intentRow = DB::table('zone_automation_intents')
            ->where('idempotency_key', $idempotencyKey)
            ->first();

        $this->assertNotNull($intentRow);
        $payloadRaw = $intentRow->payload ?? null;
        $payload = is_string($payloadRaw)
            ? json_decode($payloadRaw, true, 512, JSON_THROW_ON_ERROR)
            : (is_array($payloadRaw) ? $payloadRaw : []);

        $this->assertIsArray($payload);
        $this->assertSame('laravel_grow_cycle_start', $payload['source'] ?? null);
        $this->assertSame('diagnostics', $payload['task_type'] ?? null);
        $this->assertSame('cycle_start', $payload['workflow'] ?? null);
        $this->assertSame('two_tank_drip_substrate_trays', $payload['topology'] ?? null);
        $this->assertSame($cycleId, $payload['grow_cycle_id'] ?? null);
        $this->assertArrayNotHasKey('task_payload', $payload);
        $this->assertArrayNotHasKey('schedule_payload', $payload);

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

        $service = new class($runtimeConfig, app(AutomationConfigDocumentService::class)) extends GrowCycleService {
            /** @var array<string, mixed> */
            public array $dispatchState = [];

            protected function isGrowCycleStartDispatchEnabled(): bool
            {
                return true;
            }

            protected function postAutomationStartCycle(int $zoneId, string $idempotencyKey, array $cfg): array
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
        $this->assertTrue($service->dispatchState['start_snapshot_exists']);
        $this->assertTrue($service->dispatchState['bundle_exists']);
        $this->assertSame('RUNNING', $service->dispatchState['cycle_status']);
        $this->assertNotSame('', (string) $service->dispatchState['bundle_revision']);
        $this->assertSame($phase->id, $service->dispatchState['start_snapshot_phase_id']);
        $this->assertSame($phase->id, $service->dispatchState['bundle_phase_id']);
        $this->assertSame(
            $service->dispatchState['bundle_revision'],
            $service->dispatchState['cycle_settings_bundle_revision']
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
        $service = new class($runtimeConfig, app(AutomationConfigDocumentService::class)) extends GrowCycleService {
            protected function isGrowCycleStartDispatchEnabled(): bool
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

            protected function postAutomationStartCycle(int $zoneId, string $idempotencyKey, array $cfg): array
            {
                throw new \RuntimeException('automation_engine_start_cycle_http_error_v2:500:boom');
            }
        };

        $cycle = $service->createCycle($zone, $revision, $plant->id);
        $startedCycle = $service->startCycle($cycle, Carbon::now());

        $this->assertSame(GrowCycleStatus::RUNNING, $startedCycle->status);
        $this->assertSame('RUNNING', $zone->fresh()->status);
        $this->assertDatabaseHas('grow_cycles', [
            'id' => $cycle->id,
            'status' => GrowCycleStatus::RUNNING->value,
        ]);
        $this->assertDatabaseHas('zone_automation_intents', [
            'zone_id' => $zone->id,
            'status' => 'pending',
        ]);
    }
}
