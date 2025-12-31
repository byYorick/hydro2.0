<?php

namespace Tests\Feature;

use App\Models\GrowCycle;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\User;
use App\Models\Zone;
use App\Enums\GrowCycleStatus;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Gate;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

class GrowCyclePolicyTest extends TestCase
{
    use RefreshDatabase;

    private User $agronomist;
    private User $operator;
    private User $viewer;
    private Zone $zone;
    private GrowCycle $cycle;

    protected function setUp(): void
    {
        parent::setUp();
        $this->agronomist = User::factory()->create(['role' => 'agronomist']);
        $this->operator = User::factory()->create(['role' => 'operator']);
        $this->viewer = User::factory()->create(['role' => 'viewer']);
        $this->zone = Zone::factory()->create();
        
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $this->cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);
    }

    // Удален пример теста - используем реальные тесты ниже

    #[Test]
    public function agronomist_can_manage_cycles()
    {
        $this->assertTrue(Gate::forUser($this->agronomist)->allows('manage', GrowCycle::class));
    }

    #[Test]
    public function operator_cannot_manage_cycles()
    {
        $this->assertFalse(Gate::forUser($this->operator)->allows('manage', GrowCycle::class));
    }

    #[Test]
    public function agronomist_can_create_cycle()
    {
        $this->assertTrue(Gate::forUser($this->agronomist)->allows('create', [GrowCycle::class, $this->zone]));
    }

    #[Test]
    public function operator_cannot_create_cycle()
    {
        $this->assertFalse(Gate::forUser($this->operator)->allows('create', [GrowCycle::class, $this->zone]));
    }

    #[Test]
    public function agronomist_can_update_cycle()
    {
        $this->assertTrue(Gate::forUser($this->agronomist)->allows('update', $this->cycle));
    }

    #[Test]
    public function operator_cannot_update_cycle()
    {
        $this->assertFalse(Gate::forUser($this->operator)->allows('update', $this->cycle));
    }

    #[Test]
    public function anyone_can_view_cycle()
    {
        $this->assertTrue(Gate::forUser($this->agronomist)->allows('view', $this->cycle));
        $this->assertTrue(Gate::forUser($this->operator)->allows('view', $this->cycle));
        $this->assertTrue(Gate::forUser($this->viewer)->allows('view', $this->cycle));
    }

    #[Test]
    public function agronomist_can_switch_phase()
    {
        $this->assertTrue(Gate::forUser($this->agronomist)->allows('switchPhase', $this->cycle));
    }

    #[Test]
    public function operator_cannot_switch_phase()
    {
        $this->assertFalse(Gate::forUser($this->operator)->allows('switchPhase', $this->cycle));
    }

    #[Test]
    public function agronomist_can_change_recipe_revision()
    {
        $this->assertTrue(Gate::forUser($this->agronomist)->allows('changeRecipeRevision', $this->cycle));
    }

    #[Test]
    public function operator_cannot_change_recipe_revision()
    {
        $this->assertFalse(Gate::forUser($this->operator)->allows('changeRecipeRevision', $this->cycle));
    }
}
