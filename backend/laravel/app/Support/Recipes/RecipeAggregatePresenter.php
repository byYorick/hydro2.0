<?php

namespace App\Support\Recipes;

use App\Models\Recipe;
use App\Models\RecipeRevisionPhase;
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
        $phases = $revisionForCount?->phases;

        return [
            'id' => $recipe->id,
            'name' => $recipe->name,
            'description' => $recipe->description,
            'phases_count' => $phases?->count() ?? 0,
            'total_duration_hours' => $this->sumDurationHours($phases),
            'phases_preview' => $this->presentPhasesPreview($phases),
            'latest_published_revision_id' => $published?->id,
            'latest_draft_revision_id' => $draft?->id,
            'draft_revision_id' => $draft?->id,
            'active_zones_count' => (int) ($recipe->active_zones_count ?? 0),
            'plants' => $recipe->plants->map(fn ($plant): array => [
                'id' => $plant->id,
                'name' => $plant->name,
            ])->values()->all(),
        ];
    }

    /**
     * Суммарная длительность рецепта в часах; null, если ни одна фаза её не задаёт.
     *
     * @param  Collection<int, RecipeRevisionPhase>|null  $phases
     */
    private function sumDurationHours(?Collection $phases): ?int
    {
        if ($phases === null || $phases->isEmpty()) {
            return null;
        }

        $known = $phases
            ->map(fn ($phase) => $this->resolveDurationHours($phase))
            ->filter(fn (?int $hours): bool => $hours !== null);

        return $known->isEmpty() ? null : (int) $known->sum();
    }

    /**
     * Компактное превью фаз для мини-таймлайна в списке рецептов.
     *
     * @param  Collection<int, RecipeRevisionPhase>|null  $phases
     * @return array<int, array{phase_index: int, name: string|null, duration_hours: int|null}>
     */
    private function presentPhasesPreview(?Collection $phases): array
    {
        if ($phases === null) {
            return [];
        }

        return $phases
            ->sortBy('phase_index')
            ->map(fn ($phase): array => [
                'phase_index' => (int) $phase->phase_index,
                'name' => $phase->name,
                'duration_hours' => $this->resolveDurationHours($phase),
            ])
            ->values()
            ->all();
    }

    private function resolveDurationHours(RecipeRevisionPhase $phase): ?int
    {
        if ($phase->duration_hours !== null) {
            return (int) $phase->duration_hours;
        }

        if ($phase->duration_days !== null) {
            return (int) round(((float) $phase->duration_days) * 24);
        }

        return null;
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
