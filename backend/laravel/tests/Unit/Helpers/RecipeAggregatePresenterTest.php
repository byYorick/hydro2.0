<?php

namespace Tests\Unit\Helpers;

use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Support\Recipes\RecipeAggregatePresenter;
use App\Support\Recipes\RecipePhasePayloadNormalizer;
use App\Support\Recipes\RecipePhasePresenter;
use Illuminate\Support\Collection;
use Tests\TestCase;

class RecipeAggregatePresenterTest extends TestCase
{
    /**
     * @param  array<int, array<string, mixed>>  $phaseAttributes
     */
    private function makeRecipe(array $phaseAttributes): Recipe
    {
        $phases = new Collection(array_map(
            fn (array $attributes): RecipeRevisionPhase => new RecipeRevisionPhase($attributes),
            $phaseAttributes,
        ));

        $revision = new RecipeRevision(['revision_number' => 1, 'status' => 'PUBLISHED']);
        $revision->setRelation('phases', $phases);

        $recipe = new Recipe(['name' => 'Томат черри']);
        $recipe->setRelation('latestPublishedRevision', $revision);
        $recipe->setRelation('latestDraftRevision', null);
        $recipe->setRelation('plants', new Collection);

        return $recipe;
    }

    private function makePresenter(): RecipeAggregatePresenter
    {
        return new RecipeAggregatePresenter(new RecipePhasePresenter(new RecipePhasePayloadNormalizer));
    }

    public function test_list_item_sums_total_duration_across_phases(): void
    {
        $recipe = $this->makeRecipe([
            ['phase_index' => 0, 'name' => 'Проращивание', 'duration_hours' => 96],
            ['phase_index' => 1, 'name' => 'Вегетация', 'duration_hours' => 336],
        ]);

        $presented = $this->makePresenter()->presentListItem($recipe);

        $this->assertSame(2, $presented['phases_count']);
        $this->assertSame(432, $presented['total_duration_hours']);
    }

    public function test_list_item_derives_duration_from_days_when_hours_missing(): void
    {
        $recipe = $this->makeRecipe([
            ['phase_index' => 0, 'name' => 'Проращивание', 'duration_days' => 4],
        ]);

        $presented = $this->makePresenter()->presentListItem($recipe);

        $this->assertSame(96, $presented['total_duration_hours']);
        $this->assertSame(96, $presented['phases_preview'][0]['duration_hours']);
    }

    public function test_list_item_returns_phases_preview_sorted_by_index(): void
    {
        $recipe = $this->makeRecipe([
            ['phase_index' => 1, 'name' => 'Вегетация', 'duration_hours' => 336],
            ['phase_index' => 0, 'name' => 'Проращивание', 'duration_hours' => 96],
        ]);

        $preview = $this->makePresenter()->presentListItem($recipe)['phases_preview'];

        $this->assertSame(['Проращивание', 'Вегетация'], array_column($preview, 'name'));
        $this->assertSame([0, 1], array_column($preview, 'phase_index'));
    }

    public function test_list_item_returns_null_duration_when_no_phase_defines_it(): void
    {
        $recipe = $this->makeRecipe([
            ['phase_index' => 0, 'name' => 'Проращивание'],
        ]);

        $presented = $this->makePresenter()->presentListItem($recipe);

        $this->assertNull($presented['total_duration_hours']);
        $this->assertNull($presented['phases_preview'][0]['duration_hours']);
    }

    public function test_list_item_handles_recipe_without_revisions(): void
    {
        $recipe = new Recipe(['name' => 'Пустой']);
        $recipe->setRelation('latestPublishedRevision', null);
        $recipe->setRelation('latestDraftRevision', null);
        $recipe->setRelation('plants', new Collection);

        $presented = $this->makePresenter()->presentListItem($recipe);

        $this->assertSame(0, $presented['phases_count']);
        $this->assertNull($presented['total_duration_hours']);
        $this->assertSame([], $presented['phases_preview']);
    }
}
