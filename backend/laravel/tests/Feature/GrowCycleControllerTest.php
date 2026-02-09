<?php

namespace Tests\Feature;

use App\Enums\GrowCycleStatus;
use App\Models\ChannelBinding;
use App\Models\GrowCycle;
use App\Models\DeviceNode;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use App\Models\Zone;
use App\Services\GrowCycleService;
use Tests\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

class GrowCycleControllerTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    private Zone $zone;

    private Plant $plant;

    private Recipe $recipe;

    private RecipeRevision $revision;

    protected function setUp(): void
    {
        parent::setUp();
        $this->user = User::factory()->create(['role' => 'agronomist']);
        $this->zone = Zone::factory()->create();
        $this->plant = Plant::factory()->create();
        $this->recipe = Recipe::factory()->create();
        $this->revision = RecipeRevision::factory()->create([
            'recipe_id' => $this->recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $this->revision->id,
            'phase_index' => 0,
        ]);

        $this->attachRequiredInfrastructure($this->zone);
    }

    private function attachRequiredInfrastructure(Zone $zone): void
    {
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);

        $mainPumpChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_main',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
        ]);

        $drainChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'drain_main',
            'type' => 'actuator',
            'metric' => 'valve',
            'unit' => null,
            'config' => [],
        ]);

        $this->bindChannelToRole($zone, $mainPumpChannel, 'main_pump', 'Основная помпа');
        $this->bindChannelToRole($zone, $drainChannel, 'drain', 'Дренаж');
    }

    private function bindChannelToRole(
        Zone $zone,
        NodeChannel $channel,
        string $role,
        string $label
    ): void {
        $instance = InfrastructureInstance::query()->firstOrCreate(
            [
                'owner_type' => 'zone',
                'owner_id' => $zone->id,
                'label' => $label,
            ],
            [
                'asset_type' => 'PUMP',
                'required' => true,
            ]
        );

        ChannelBinding::query()->updateOrCreate(
            ['node_channel_id' => $channel->id],
            [
                'infrastructure_instance_id' => $instance->id,
                'direction' => 'actuator',
                'role' => $role,
            ]
        );
    }

    #[Test]
    public function it_creates_a_grow_cycle(): void
    {
        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => false,
            ]);

        $response->assertStatus(201)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'id',
                    'zone_id',
                    'recipe_revision_id',
                    'status',
                ],
            ]);

        $this->assertDatabaseHas('grow_cycles', [
            'zone_id' => $this->zone->id,
            'recipe_revision_id' => $this->revision->id,
            'status' => GrowCycleStatus::PLANNED->value,
        ]);
    }

    #[Test]
    public function it_creates_and_starts_cycle_immediately(): void
    {
        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => true,
            ]);

        $response->assertStatus(201);

        $cycle = GrowCycle::where('zone_id', $this->zone->id)->first();
        $this->assertEquals(GrowCycleStatus::RUNNING, $cycle->status);
        $this->assertNotNull($cycle->planting_at);
        $this->assertSame('RUNNING', $this->zone->fresh()->status);
    }

    #[Test]
    public function it_blocks_cycle_start_when_zone_has_no_bound_nodes(): void
    {
        $zoneWithoutNodes = Zone::factory()->create();

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$zoneWithoutNodes->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => true,
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Zone is not ready for cycle start')
            ->assertJsonPath('readiness.nodes.total', 0);

        $errors = $response->json('readiness_errors', []);
        $this->assertContains('Нет привязанных нод в зоне', $errors);
    }

    #[Test]
    public function it_blocks_cycle_start_when_ec_control_is_enabled_but_ec_pumps_are_missing(): void
    {
        $ecZone = Zone::factory()->create([
            'capabilities' => [
                'ec_control' => true,
                'ph_control' => false,
            ],
        ]);
        $this->attachRequiredInfrastructure($ecZone);

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$ecZone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => true,
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Zone is not ready for cycle start');

        $errors = $response->json('readiness_errors', []);
        $this->assertContains('Насос EC NPK не привязан к каналу', $errors);
        $this->assertContains('Насос EC Calcium не привязан к каналу', $errors);
        $this->assertContains('Насос EC Magnesium не привязан к каналу', $errors);
        $this->assertContains('Насос EC Micro не привязан к каналу', $errors);
    }

    #[Test]
    public function it_gets_active_cycle_with_dto(): void
    {
        $service = app(GrowCycleService::class);
        $cycle = $service->createCycle($this->zone, $this->revision, $this->plant->id, ['start_immediately' => true]);

        $response = $this->actingAs($this->user)
            ->getJson("/api/zones/{$this->zone->id}/grow-cycle");

        $response->assertStatus(200)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'cycle' => [
                        'id',
                        'status',
                        'planting_at',
                        'current_stage',
                        'progress',
                        'stages',
                    ],
                    'effective_targets',
                ],
            ]);
    }

    #[Test]
    public function it_advances_phase(): void
    {
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $this->revision->id,
            'phase_index' => 1,
        ]);

        $service = app(GrowCycleService::class);
        $cycle = $service->createCycle($this->zone, $this->revision, $this->plant->id, ['start_immediately' => true]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/advance-phase");

        $response->assertStatus(200);
        $cycle->refresh();
        $this->assertEquals(1, $cycle->currentPhase->phase_index);
    }

    #[Test]
    public function it_pauses_a_cycle(): void
    {
        $this->zone->update(['status' => 'RUNNING']);
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/pause");

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::PAUSED, $cycle->status);
        $this->assertSame('PAUSED', $this->zone->fresh()->status);
    }

    #[Test]
    public function it_resumes_a_cycle(): void
    {
        $this->zone->update(['status' => 'PAUSED']);
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::PAUSED,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/resume");

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::RUNNING, $cycle->status);
        $this->assertSame('RUNNING', $this->zone->fresh()->status);
    }

    #[Test]
    public function it_harvests_a_cycle(): void
    {
        $this->zone->update(['status' => 'RUNNING']);
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/harvest", [
                'batch_label' => 'Batch-001',
            ]);

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::HARVESTED, $cycle->status);
        $this->assertEquals('Batch-001', $cycle->batch_label);
        $this->assertNotNull($cycle->actual_harvest_at);
        $this->assertSame('NEW', $this->zone->fresh()->status);
    }

    #[Test]
    public function it_aborts_a_cycle(): void
    {
        $this->zone->update(['status' => 'RUNNING']);
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/abort", [
                'notes' => 'Emergency stop',
            ]);

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::ABORTED, $cycle->status);
        $this->assertSame('NEW', $this->zone->fresh()->status);
    }

    #[Test]
    public function it_returns_422_when_pausing_non_running_cycle(): void
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::PLANNED,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/pause");

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cycle is not running');
    }

    #[Test]
    public function it_returns_422_when_resuming_non_paused_cycle(): void
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/resume");

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cycle is not paused');
    }

    #[Test]
    public function it_returns_422_when_harvesting_completed_cycle(): void
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::HARVESTED,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/harvest", [
                'batch_label' => 'Batch-002',
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cycle is already completed');
    }

    #[Test]
    public function it_returns_422_when_aborting_completed_cycle(): void
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::ABORTED,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/abort", [
                'notes' => 'Already stopped',
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cycle is already completed');
    }
}
