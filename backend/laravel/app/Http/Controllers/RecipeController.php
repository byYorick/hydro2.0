<?php

namespace App\Http\Controllers;

use App\Enums\GrowCycleStatus;
use App\Models\GrowCycle;
use App\Models\Recipe;
use App\Services\RecipeService;
use App\Support\Recipes\RecipeAggregatePresenter;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class RecipeController extends Controller
{
    public function __construct(
        private RecipeService $recipeService,
        private RecipeAggregatePresenter $presenter,
    ) {}

    public function index(Request $request): JsonResponse
    {
        // Валидация query параметров
        $validated = $request->validate([
            'search' => ['nullable', 'string', 'max:255'],
            'per_page' => ['nullable', 'integer', 'min:1', 'max:200'],
        ]);

        $query = Recipe::query()->with([
            'latestPublishedRevision.phases',
            'latestDraftRevision.phases',
            'plants:id,name',
        ]);

        // Поиск по имени или описанию
        if (isset($validated['search']) && $validated['search']) {
            // Экранируем специальные символы LIKE для защиты от SQL injection
            $searchTerm = addcslashes($validated['search'], '%_');
            $query->where(function ($q) use ($searchTerm) {
                $q->where('name', 'ILIKE', "%{$searchTerm}%")
                    ->orWhere('description', 'ILIKE', "%{$searchTerm}%");
            });
        }

        $perPage = (int) ($validated['per_page'] ?? 25);
        $items = $query->latest('id')->paginate($perPage);

        $items->setCollection(
            $items->getCollection()->map(fn (Recipe $recipe) => $this->presenter->presentListItem($recipe))
        );

        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function store(Request $request): JsonResponse
    {
        $data = $request->validate([
            'name' => ['required', 'string', 'max:255'],
            'description' => ['nullable', 'string'],
            'plant_id' => ['required', 'integer', 'exists:plants,id'],
        ]);

        $recipe = $this->recipeService->create($data, $data['plant_id']);

        return response()->json(['status' => 'ok', 'data' => $recipe], Response::HTTP_CREATED);
    }

    public function show(Recipe $recipe): JsonResponse
    {
        $recipe->load([
            'latestPublishedRevision.phases',
            'latestDraftRevision.phases',
            'plants:id,name',
        ]);

        $recipe->loadMissing([
            'latestDraftRevision.phases.stageTemplate',
            'latestPublishedRevision.phases.stageTemplate',
        ]);

        return response()->json(['status' => 'ok', 'data' => $this->presenter->presentDetail($recipe)]);
    }

    /**
     * Список активных grow-cycle, использующих этот рецепт.
     * Используется фронтом для предупреждения "рецепт активен в зоне".
     * GET /api/recipes/{recipe}/active-usage
     */
    public function activeUsage(Recipe $recipe): JsonResponse
    {
        $cycles = GrowCycle::query()
            ->with(['zone:id,name', 'recipeRevision:id,recipe_id,revision_number,status'])
            ->whereHas('recipeRevision', fn ($q) => $q->where('recipe_id', $recipe->id))
            ->whereIn('status', [GrowCycleStatus::PLANNED, GrowCycleStatus::RUNNING, GrowCycleStatus::PAUSED])
            ->get(['id', 'zone_id', 'recipe_revision_id', 'status', 'started_at']);

        $items = $cycles->map(fn (GrowCycle $cycle) => [
            'cycle_id' => $cycle->id,
            'zone_id' => $cycle->zone_id,
            'zone_name' => $cycle->zone?->name,
            'revision_id' => $cycle->recipe_revision_id,
            'revision_number' => $cycle->recipeRevision?->revision_number,
            'status' => $cycle->status->value,
            'started_at' => $cycle->started_at,
        ]);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'recipe_id' => $recipe->id,
                'active_cycles' => $items,
                'count' => $items->count(),
            ],
        ]);
    }

    /**
     * Получить stage-map рецепта
     */
    public function getStageMap(Recipe $recipe): JsonResponse
    {
        $recipe->load(['latestPublishedRevision.phases', 'latestDraftRevision.phases']);

        $phases = $recipe->latestPublishedRevision?->phases
            ?? $recipe->latestDraftRevision?->phases
            ?? collect();

        // Получаем stage-map из metadata или генерируем автоматически
        $stageMap = $recipe->metadata['stage_map'] ?? null;

        // Если нет stage-map, генерируем автоматически на основе названий фаз
        if (! $stageMap && $phases->count() > 0) {
            $stageMap = [];
            foreach ($phases as $phase) {
                $stageMap[] = [
                    'phase_index' => $phase->phase_index,
                    'phase_name' => $phase->name,
                    'stage' => $this->inferStageFromPhaseName($phase->name, $phase->phase_index),
                ];
            }
        }

        return response()->json([
            'status' => 'ok',
            'data' => [
                'recipe_id' => $recipe->id,
                'stage_map' => $stageMap,
            ],
        ]);
    }

    /**
     * Обновить stage-map рецепта
     */
    public function updateStageMap(Request $request, Recipe $recipe): JsonResponse
    {
        $data = $request->validate([
            'stage_map' => ['required', 'array'],
            'stage_map.*.phase_index' => ['required', 'integer'],
            'stage_map.*.stage' => ['required', 'string', 'in:planting,rooting,veg,flowering,harvest'],
        ]);

        $metadata = $recipe->metadata ?? [];
        $metadata['stage_map'] = $data['stage_map'];
        $recipe->update(['metadata' => $metadata]);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'recipe_id' => $recipe->id,
                'stage_map' => $data['stage_map'],
            ],
        ]);
    }

    /**
     * Автоматически определить стадию на основе названия фазы
     */
    private function inferStageFromPhaseName(string $phaseName, int $phaseIndex): string
    {
        $normalized = strtolower(trim($phaseName));

        $mapping = [
            'planting' => ['посадка', 'посев', 'germination', 'germ', 'seed', 'семена'],
            'rooting' => ['укоренение', 'rooting', 'root', 'seedling', 'рассада', 'ростки'],
            'veg' => ['вега', 'вегетация', 'vegetative', 'veg', 'growth', 'рост', 'вегетативный'],
            'flowering' => ['цветение', 'flowering', 'flower', 'bloom', 'blooming', 'цвет'],
            'harvest' => ['сбор', 'harvest', 'finishing', 'finish', 'созревание', 'урожай'],
        ];

        foreach ($mapping as $stage => $keywords) {
            foreach ($keywords as $keyword) {
                if (str_contains($normalized, $keyword)) {
                    return $stage;
                }
            }
        }

        // Fallback по индексу
        $defaultStages = ['planting', 'rooting', 'veg', 'flowering', 'harvest'];

        return $defaultStages[min($phaseIndex, count($defaultStages) - 1)] ?? 'veg';
    }

    public function update(Request $request, Recipe $recipe): JsonResponse
    {
        $data = $request->validate([
            'name' => ['sometimes', 'string', 'max:255'],
            'description' => ['nullable', 'string'],
            'plant_id' => ['sometimes', 'integer', 'exists:plants,id'],
        ]);
        $recipe = $this->recipeService->update($recipe, $data);

        return response()->json(['status' => 'ok', 'data' => $recipe]);
    }

    public function destroy(Recipe $recipe): JsonResponse
    {
        try {
            $this->recipeService->delete($recipe);

            return response()->json(['status' => 'ok']);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }
}
