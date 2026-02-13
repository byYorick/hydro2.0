<?php

namespace Tests\Feature;

use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use App\Models\Zone;
use Tests\RefreshDatabase;
use Tests\TestCase;

class GrowCycleWizardControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_it_creates_cycle_and_persists_normalized_bindings_for_ph_ec_roles(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $zone = Zone::factory()->create([
            'capabilities' => [
                'ph_control' => true,
                'ec_control' => true,
            ],
        ]);
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);

        $channelsByRole = $this->createWizardChannels($node);

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

        $payload = [
            'zone_id' => $zone->id,
            'plant_id' => $plant->id,
            'recipe_revision_id' => $revision->id,
            'planting_date' => now()->toDateString(),
            'automation_start_date' => now()->toDateString(),
            'batch' => [
                'quantity' => 12,
                'density' => 4.5,
                'substrate' => 'coco',
                'system' => 'drip',
            ],
            'channel_bindings' => collect($channelsByRole)
                ->map(fn (NodeChannel $channel, string $role) => [
                    'node_id' => $node->id,
                    'channel_id' => $channel->id,
                    'role' => $role,
                ])
                ->values()
                ->all(),
        ];

        $response = $this->actingAs($user)->postJson('/api/grow-cycle-wizard/create', $payload);

        $response->assertOk()
            ->assertJsonPath('status', 'ok');

        $this->assertDatabaseHas('grow_cycles', [
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
        ]);

        foreach ($channelsByRole as $role => $channel) {
            $this->assertDatabaseHas('channel_bindings', [
                'node_channel_id' => $channel->id,
                'role' => $role,
                'direction' => 'actuator',
            ]);
        }

        $zoneBindingsCount = ChannelBinding::query()
            ->join('infrastructure_instances as ii', 'ii.id', '=', 'channel_bindings.infrastructure_instance_id')
            ->where('ii.owner_type', 'zone')
            ->where('ii.owner_id', $zone->id)
            ->count();

        $this->assertEquals(8, $zoneBindingsCount);
        $this->assertArrayNotHasKey('zone_role', $channelsByRole['ec_npk_pump']->fresh()->config ?? []);
    }

    public function test_it_rejects_unknown_wizard_binding_role(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_main',
            'type' => 'actuator',
            'metric' => 'pump',
            'unit' => null,
            'config' => [],
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

        $response = $this->actingAs($user)->postJson('/api/grow-cycle-wizard/create', [
            'zone_id' => $zone->id,
            'plant_id' => $plant->id,
            'recipe_revision_id' => $revision->id,
            'planting_date' => now()->toDateString(),
            'automation_start_date' => now()->toDateString(),
            'batch' => ['quantity' => 10],
            'channel_bindings' => [
                [
                    'node_id' => $node->id,
                    'channel_id' => $channel->id,
                    'role' => 'pump_nutrient_legacy',
                ],
            ],
        ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonStructure(['errors' => ['channel_bindings.0.role']]);
    }

    /**
     * @return array<string, NodeChannel>
     */
    private function createWizardChannels(DeviceNode $node): array
    {
        return [
            'main_pump' => $this->createChannel($node, 'pump_main', 'pump'),
            'drain' => $this->createChannel($node, 'drain_main', 'valve'),
            'ph_acid_pump' => $this->createChannel($node, 'pump_acid', 'pump'),
            'ph_base_pump' => $this->createChannel($node, 'pump_base', 'pump'),
            'ec_npk_pump' => $this->createChannel($node, 'pump_a', 'pump'),
            'ec_calcium_pump' => $this->createChannel($node, 'pump_b', 'pump'),
            'ec_magnesium_pump' => $this->createChannel($node, 'pump_c', 'pump'),
            'ec_micro_pump' => $this->createChannel($node, 'pump_d', 'pump'),
        ];
    }

    private function createChannel(DeviceNode $node, string $channel, string $metric): NodeChannel
    {
        return NodeChannel::create([
            'node_id' => $node->id,
            'channel' => $channel,
            'type' => 'actuator',
            'metric' => $metric,
            'unit' => null,
            'config' => [],
        ]);
    }
}
