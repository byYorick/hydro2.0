<?php

namespace Tests\Feature;

use App\Enums\GrowCycleStatus;
use App\Models\GrowCycle;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use App\Models\Zone;
use App\Services\AutomationScheduler\ScheduleDispatcher;
use App\Services\GrowCycleService;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use PHPUnit\Framework\Attributes\Test;
use Tests\RefreshDatabase;
use Tests\TestCase;

class HydroponicSystemCycleTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    private Zone $zone;

    private Plant $plant;

    private RecipeRevision $revision;

    protected function setUp(): void
    {
        parent::setUp();
        config()->set('services.automation_engine.grow_cycle_start_dispatch_enabled', true);
        $this->user = User::factory()->create(['role' => 'agronomist']);
        $this->zone = Zone::factory()->create();
        $this->zone->greenhouse->update(['type' => 'greenhouse']);
        $this->plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $this->revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $this->revision->id,
            'phase_index' => 0,
        ]);
    }

    #[Test]
    public function it_creates_cycle_without_explicit_system_type(): void
    {
        $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => false,
            ])
            ->assertCreated();
    }

    #[Test]
    public function it_rejects_nft_and_dwc(): void
    {
        foreach (['nft', 'dwc'] as $systemType) {
            $this->actingAs($this->user)
                ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                    'recipe_revision_id' => $this->revision->id,
                    'plant_id' => $this->plant->id,
                    'start_immediately' => true,
                    'irrigation' => ['system_type' => $systemType],
                ])
                ->assertStatus(422)
                ->assertJsonPath('code', 'hydro_system_not_implemented')
                ->assertJsonPath('requested_type', $systemType)
                ->assertJsonPath('supported_types', ['drip']);
        }

        $this->assertSame(0, GrowCycle::query()->where('zone_id', $this->zone->id)->count());
    }

    #[Test]
    public function it_rejects_substrate_trays_without_mapping_to_drip(): void
    {
        $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'irrigation' => ['system_type' => 'substrate_trays'],
            ])
            ->assertStatus(422)
            ->assertJsonPath('code', 'hydro_system_needs_review')
            ->assertJsonPath('requested_type', 'substrate_trays');
    }

    #[Test]
    public function it_rejects_resume_of_nft_cycle(): void
    {
        $this->zone->update(['status' => 'PAUSED']);
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'greenhouse_id' => $this->zone->greenhouse_id,
            'status' => GrowCycleStatus::PAUSED,
            'settings' => ['irrigation' => ['system_type' => 'nft']],
        ]);

        $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/resume")
            ->assertStatus(422)
            ->assertJsonPath('code', 'hydro_system_not_implemented')
            ->assertJsonPath('requested_type', 'nft');

        $this->assertSame(GrowCycleStatus::PAUSED, $cycle->fresh()->status);
    }

    #[Test]
    public function it_rejects_advance_onto_dwc_phase(): void
    {
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $this->revision->id,
            'phase_index' => 1,
            'irrigation_system_type' => 'dwc',
        ]);
        $cycle = app(GrowCycleService::class)->createCycle(
            $this->zone,
            $this->revision,
            $this->plant->id,
            ['start_immediately' => false],
        );

        $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/advance-phase")
            ->assertStatus(422)
            ->assertJsonPath('code', 'hydro_system_not_implemented')
            ->assertJsonPath('requested_type', 'dwc');
    }

    #[Test]
    public function it_blocks_irrigation_intent_for_nft_and_allows_lighting(): void
    {
        $this->zone->update(['automation_runtime' => 'ae3', 'status' => 'online']);
        GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'greenhouse_id' => $this->zone->greenhouse_id,
            'status' => GrowCycleStatus::RUNNING,
            'settings' => ['irrigation' => ['system_type' => 'nft']],
        ]);
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $when = CarbonImmutable::parse('2026-03-12 12:00:00', 'UTC');

        $irrigation = $dispatcher->upsertSchedulerIntent(
            zoneId: $this->zone->id,
            taskType: 'irrigation',
            correlationId: 'sch:hydro:irrigation',
            triggerTime: $when,
        );
        $this->assertFalse($irrigation['ok']);
        $this->assertSame('hydro_system_not_implemented', $irrigation['blocked_code'] ?? null);

        $lighting = $dispatcher->upsertSchedulerIntent(
            zoneId: $this->zone->id,
            taskType: 'lighting',
            correlationId: 'sch:hydro:lighting',
            triggerTime: $when,
        );
        $this->assertTrue($lighting['ok']);
        $this->assertSame(0, DB::table('zone_automation_intents')->where('zone_id', $this->zone->id)->where('task_type', 'irrigation_start')->count());
    }
}
