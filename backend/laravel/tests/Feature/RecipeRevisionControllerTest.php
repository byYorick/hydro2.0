<?php

namespace Tests\Feature;

use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use Tests\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

class RecipeRevisionControllerTest extends TestCase
{
    use RefreshDatabase;

    private User $agronomist;
    private User $operator;
    private Recipe $recipe;

    protected function setUp(): void
    {
        parent::setUp();
        $this->agronomist = User::factory()->create(['role' => 'agronomist']);
        $this->operator = User::factory()->create(['role' => 'operator']);
        $this->recipe = Recipe::factory()->create();
    }

    // Удален пример теста - используем реальные тесты ниже

    #[Test]
    public function it_shows_recipe_revision_with_phases()
    {
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $this->recipe->id,
            'status' => 'PUBLISHED',
        ]);

        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Test Phase 1',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 1,
            'name' => 'Test Phase 2',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 2,
            'name' => 'Test Phase 3',
        ]);

        $response = $this->actingAs($this->agronomist)
            ->getJson("/api/recipe-revisions/{$revision->id}");

        $response->assertStatus(200)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'id',
                    'recipe_id',
                    'revision_number',
                    'status',
                    'phases' => [
                        '*' => [
                            'id',
                            'phase_index',
                            'name',
                        ],
                    ],
                ],
            ]);
    }

    #[Test]
    public function it_creates_new_revision_from_existing()
    {
        $sourceRevision = RecipeRevision::factory()->create([
            'recipe_id' => $this->recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $template = \App\Models\GrowStageTemplate::factory()->create();
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $sourceRevision->id,
            'stage_template_id' => $template->id,
            'phase_index' => 0,
            'name' => 'Test Phase 1',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $sourceRevision->id,
            'stage_template_id' => $template->id,
            'phase_index' => 1,
            'name' => 'Test Phase 2',
        ]);

        $response = $this->actingAs($this->agronomist)
            ->postJson("/api/recipes/{$this->recipe->id}/revisions", [
                'clone_from_revision_id' => $sourceRevision->id,
                'description' => 'New revision based on published',
            ]);

        $response->assertStatus(201)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'id',
                    'recipe_id',
                    'revision_number',
                    'status',
                ],
            ]);

        $this->assertDatabaseHas('recipe_revisions', [
            'recipe_id' => $this->recipe->id,
            'status' => 'DRAFT',
        ]);

        // Проверяем, что фазы скопированы
        $newRevision = RecipeRevision::where('recipe_id', $this->recipe->id)
            ->where('status', 'DRAFT')
            ->first();
        $this->assertEquals(2, $newRevision->phases()->count());
    }

    #[Test]
    public function it_updates_draft_revision()
    {
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $this->recipe->id,
            'status' => 'DRAFT',
            'created_by' => $this->agronomist->id,
        ]);

        $response = $this->actingAs($this->agronomist)
            ->patchJson("/api/recipe-revisions/{$revision->id}", [
                'description' => 'Updated description',
            ]);

        $response->assertStatus(200);

        $revision->refresh();
        $this->assertEquals('Updated description', $revision->description);
    }

    #[Test]
    public function it_publishes_draft_revision()
    {
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $this->recipe->id,
            'status' => 'DRAFT',
            'created_by' => $this->agronomist->id,
        ]);

        // Добавляем фазу, так как публикация требует хотя бы одну фазу
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'name' => 'Test Phase',
        ]);

        $response = $this->actingAs($this->agronomist)
            ->postJson("/api/recipe-revisions/{$revision->id}/publish");

        $response->assertStatus(200);

        $revision->refresh();
        $this->assertEquals('PUBLISHED', $revision->status);
        $this->assertNotNull($revision->published_at);
    }

    #[Test]
    public function it_prevents_non_agronomist_from_creating_revision()
    {
        $response = $this->actingAs($this->operator)
            ->postJson("/api/recipes/{$this->recipe->id}/revisions", [
                'description' => 'Test',
            ]);

        $response->assertStatus(403)
            ->assertJson([
                'status' => 'error',
                'message' => 'Forbidden: Only agronomists can create recipe revisions',
            ]);
    }

    #[Test]
    public function it_prevents_updating_published_revision()
    {
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $this->recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $response = $this->actingAs($this->agronomist)
            ->patchJson("/api/recipe-revisions/{$revision->id}", [
                'description' => 'Try to update',
            ]);

        // Policy блокирует доступ к опубликованной ревизии (403), а не валидация (422)
        $response->assertStatus(403)
            ->assertJson([
                'status' => 'error',
            ]);
    }
}
