<?php

namespace App\Http\Controllers;

use App\Models\Recipe;
use App\Services\RecipeService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class RecipeController extends Controller
{
    public function __construct(
        private RecipeService $recipeService
    ) {}

    public function index(Request $request): JsonResponse
    {
        // Валидация query параметров
        $validated = $request->validate([
            'search' => ['nullable', 'string', 'max:255'],
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

        $items = $query->latest('id')->paginate(25);

        $items->getCollection()->transform(function (Recipe $recipe) {
            $published = $recipe->latestPublishedRevision;
            $draft = $recipe->latestDraftRevision;
            $revisionForCount = $published ?? $draft;

            return [
                'id' => $recipe->id,
                'name' => $recipe->name,
                'description' => $recipe->description,
                'phases_count' => $revisionForCount?->phases?->count() ?? 0,
                'latest_published_revision_id' => $published?->id,
                'latest_draft_revision_id' => $draft?->id,
                'plants' => $recipe->plants->map(fn ($plant) => [
                    'id' => $plant->id,
                    'name' => $plant->name,
                ]),
            ];
        });

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

        $recipeArray = $recipe->toArray();
        $recipeArray['latest_published_revision_id'] = $recipe->latestPublishedRevision?->id;
        $recipeArray['latest_draft_revision_id'] = $recipe->latestDraftRevision?->id;
        $recipeArray['phases'] = $recipe->latestDraftRevision?->phases?->toArray()
            ?? $recipe->latestPublishedRevision?->phases?->toArray()
            ?? [];
        $recipeArray['plants'] = $recipe->plants->map(fn ($plant) => [
            'id' => $plant->id,
            'name' => $plant->name,
        ])->toArray();

        return response()->json(['status' => 'ok', 'data' => $recipeArray]);
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
