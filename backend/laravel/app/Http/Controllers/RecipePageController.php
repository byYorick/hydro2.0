<?php

namespace App\Http\Controllers;

use App\Models\Recipe;
use App\Support\Recipes\RecipeAggregatePresenter;
use Inertia\Inertia;
use Inertia\Response;

class RecipePageController extends Controller
{
    public function __construct(
        private readonly RecipeAggregatePresenter $presenter
    ) {}

    public function index(): Response
    {
        $recipes = Recipe::query()
            ->with([
                'latestPublishedRevision.phases',
                'latestDraftRevision.phases',
                'plants:id,name',
            ])
            ->latest('id')
            ->get();

        return Inertia::render('Recipes/Index', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'recipes' => $this->presenter->presentList($recipes),
        ]);
    }

    public function create(\Illuminate\Http\Request $request): Response
    {
        $plants = [];
        $plantIdParam = $request->query('plant_id');
        if ($plantIdParam !== null && ctype_digit((string) $plantIdParam)) {
            $plant = \App\Models\Plant::query()->find((int) $plantIdParam);
            if ($plant) {
                $plants[] = ['id' => $plant->id, 'name' => $plant->name];
            }
        }

        return Inertia::render('Recipes/Edit', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'recipe' => [
                'id' => null,
                'name' => '',
                'description' => '',
                'plants' => $plants,
                'phases' => [],
                'latest_published_revision_id' => null,
                'latest_draft_revision_id' => null,
                'draft_revision_id' => null,
            ],
        ]);
    }

    public function show(Recipe $recipe): Response
    {
        $recipe->load([
            'latestDraftRevision.phases.stageTemplate',
            'latestPublishedRevision.phases.stageTemplate',
            'latestPublishedRevision.phases.npkProduct:id,manufacturer,name,component',
            'latestPublishedRevision.phases.calciumProduct:id,manufacturer,name,component',
            'latestPublishedRevision.phases.magnesiumProduct:id,manufacturer,name,component',
            'latestPublishedRevision.phases.microProduct:id,manufacturer,name,component',
            'latestDraftRevision.phases.npkProduct:id,manufacturer,name,component',
            'latestDraftRevision.phases.calciumProduct:id,manufacturer,name,component',
            'latestDraftRevision.phases.magnesiumProduct:id,manufacturer,name,component',
            'latestDraftRevision.phases.microProduct:id,manufacturer,name,component',
            'plants:id,name',
        ]);

        return Inertia::render('Recipes/Show', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'recipe' => $this->presenter->presentDetail($recipe),
        ]);
    }

    public function edit(Recipe $recipe): Response
    {
        $recipe->load([
            'latestDraftRevision.phases.stageTemplate',
            'latestDraftRevision.phases.npkProduct:id,manufacturer,name,component',
            'latestDraftRevision.phases.calciumProduct:id,manufacturer,name,component',
            'latestDraftRevision.phases.magnesiumProduct:id,manufacturer,name,component',
            'latestDraftRevision.phases.microProduct:id,manufacturer,name,component',
            'latestPublishedRevision.phases.stageTemplate',
            'latestPublishedRevision.phases.npkProduct:id,manufacturer,name,component',
            'latestPublishedRevision.phases.calciumProduct:id,manufacturer,name,component',
            'latestPublishedRevision.phases.magnesiumProduct:id,manufacturer,name,component',
            'latestPublishedRevision.phases.microProduct:id,manufacturer,name,component',
            'plants:id,name',
        ]);

        return Inertia::render('Recipes/Edit', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'recipe' => $this->presenter->presentDetail($recipe),
        ]);
    }
}
