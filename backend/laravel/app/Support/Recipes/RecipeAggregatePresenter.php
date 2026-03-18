<?php

namespace App\Support\Recipes;

use App\Models\Recipe;
use Illuminate\Support\Collection;

class RecipeAggregatePresenter
{
    public function __construct(
        private readonly RecipePhasePresenter $phasePresenter
    ) {}

    /**
     * @param  Collection<int, Recipe>  $recipes
     * @return array<int, array<string, mixed>>
     */
    public function presentList(Collection $recipes): array
    {
        return $recipes
            ->map(fn (Recipe $recipe): array => $this->presentListItem($recipe))
            ->values()
            ->all();
    }

    /**
     * @return array<string, mixed>
     */
    public function presentListItem(Recipe $recipe): array
    {
        $published = $recipe->latestPublishedRevision;
        $draft = $recipe->latestDraftRevision;
        $revisionForCount = $draft ?? $published;

        return [
            'id' => $recipe->id,
            'name' => $recipe->name,
            'description' => $recipe->description,
            'phases_count' => $revisionForCount?->phases?->count() ?? 0,
            'latest_published_revision_id' => $published?->id,
            'latest_draft_revision_id' => $draft?->id,
            'draft_revision_id' => $draft?->id,
            'plants' => $recipe->plants->map(fn ($plant): array => [
                'id' => $plant->id,
                'name' => $plant->name,
            ])->values()->all(),
        ];
    }

    /**
     * @return array<string, mixed>
     */
    public function presentDetail(Recipe $recipe): array
    {
        $published = $recipe->latestPublishedRevision;
        $draft = $recipe->latestDraftRevision;
        $phaseSource = $draft ?? $published;

        return [
            'id' => $recipe->id,
            'name' => $recipe->name,
            'description' => $recipe->description,
            'metadata' => $recipe->metadata,
            'latest_published_revision_id' => $published?->id,
            'latest_draft_revision_id' => $draft?->id,
            'draft_revision_id' => $draft?->id,
            'plants' => $recipe->plants->map(fn ($plant): array => [
                'id' => $plant->id,
                'name' => $plant->name,
            ])->values()->all(),
            'phases' => $phaseSource?->phases
                ? $phaseSource->phases->map(fn ($phase): array => $this->phasePresenter->present($phase))->values()->all()
                : [],
        ];
    }
}
