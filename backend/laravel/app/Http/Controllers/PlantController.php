<?php

namespace App\Http\Controllers;

use App\Http\Requests\StorePlantPriceRequest;
use App\Http\Requests\StorePlantRequest;
use App\Http\Requests\UpdatePlantTaxonomyRequest;
use App\Http\Requests\UpdatePlantRequest;
use App\Models\Plant;
use App\Services\Profitability\ProfitabilityCalculator;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Arr;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Str;
use Inertia\Inertia;
use Inertia\Response;

class PlantController extends Controller
{
    public function __construct(private readonly ProfitabilityCalculator $profitability) {}

    public function index(Request $request): Response|JsonResponse
    {
        $plants = Plant::query()
            ->with([
                'priceVersions.costItems',
                'priceVersions.salePrices',
                'costItems',
                'salePrices',
            ])
            ->orderBy('name')
            ->get()
            ->map(function (Plant $plant) {
                $profitability = $this->profitability->calculatePlant($plant);

                return [
                    'id' => $plant->id,
                    'slug' => $plant->slug,
                    'name' => $plant->name,
                    'species' => $plant->species,
                    'variety' => $plant->variety,
                    'substrate_type' => $plant->substrate_type,
                    'growing_system' => $plant->growing_system,
                    'photoperiod_preset' => $plant->photoperiod_preset,
                    'seasonality' => $plant->seasonality,
                    'description' => $plant->description,
                    'environment_requirements' => $plant->environment_requirements,
                    'growth_phases' => $plant->growth_phases,
                    'recommended_recipes' => $plant->recommended_recipes,
                    'created_at' => $plant->created_at,
                    'profitability' => $profitability,
                ];
            });

        // Если это API запрос, возвращаем JSON
        if ($request->wantsJson() || $request->expectsJson()) {
            return response()->json([
                'status' => 'ok',
                'data' => $plants,
            ]);
        }

        return Inertia::render('Plants/Index', [
            'plants' => $plants,
            'taxonomies' => $this->loadTaxonomies(),
        ]);
    }

    public function show(Request $request, Plant $plant): Response|JsonResponse
    {
        $profitability = $this->profitability->calculatePlant($plant);

        // Загружаем связанные рецепты с фазами ревизий
        $plant->load([
            'recipes.latestPublishedRevision.phases',
            'recipes.latestDraftRevision.phases',
        ]);

        // Формируем данные рецептов с фазами
        $recipes = $plant->recipes->map(function ($recipe) {
            $revision = $recipe->latestPublishedRevision ?? $recipe->latestDraftRevision;
            $phases = $revision?->phases ?? collect();

            return [
                'id' => $recipe->id,
                'name' => $recipe->name,
                'description' => $recipe->description,
                'is_default' => $recipe->pivot->is_default ?? false,
                'season' => $recipe->pivot->season,
                'site_type' => $recipe->pivot->site_type,
                'phases' => $phases->map(function ($phase) {
                    return [
                        'id' => $phase->id,
                        'phase_index' => $phase->phase_index,
                        'name' => $phase->name,
                        'duration_hours' => $phase->duration_hours,
                        'targets' => $phase->targets,
                    ];
                })->sortBy('phase_index')->values(),
                'phases_count' => $phases->count(),
            ];
        });

        $plantData = [
            'id' => $plant->id,
            'slug' => $plant->slug,
            'name' => $plant->name,
            'species' => $plant->species,
            'variety' => $plant->variety,
            'substrate_type' => $plant->substrate_type,
            'growing_system' => $plant->growing_system,
            'photoperiod_preset' => $plant->photoperiod_preset,
            'seasonality' => $plant->seasonality,
            'description' => $plant->description,
            'environment_requirements' => $plant->environment_requirements,
            'growth_phases' => $plant->growth_phases,
            'recommended_recipes' => $plant->recommended_recipes,
            'recipes' => $recipes,
            'created_at' => $plant->created_at,
            'profitability' => $profitability,
        ];

        // Если это API запрос, возвращаем JSON
        if ($request->wantsJson() || $request->expectsJson()) {
            return response()->json([
                'status' => 'ok',
                'data' => $plantData,
            ]);
        }

        return Inertia::render('Plants/Show', [
            'plant' => $plantData,
            'taxonomies' => $this->loadTaxonomies(),
        ]);
    }

    public function store(StorePlantRequest $request)
    {
        $validated = $request->validated();

        // Маппинг scientific_name -> species для обратной совместимости с тестами
        if (isset($validated['scientific_name']) && ! isset($validated['species'])) {
            $validated['species'] = $validated['scientific_name'];
            unset($validated['scientific_name']);
        }

        $payload = $this->preparePayload($validated);
        $plant = Plant::create($payload);

        // Если это API запрос, возвращаем JSON
        if ($request->wantsJson() || $request->expectsJson()) {
            return response()->json([
                'status' => 'ok',
                'data' => [
                    'id' => $plant->id,
                    'name' => $plant->name,
                    'scientific_name' => $plant->species,
                    'slug' => $plant->slug,
                ],
            ], 201);
        }

        return back()->with('flash', [
            'success' => 'Растение создано',
        ]);
    }

    public function update(UpdatePlantRequest $request, Plant $plant): RedirectResponse
    {
        $payload = $this->preparePayload($request->validated(), $plant);
        $plant->update($payload);

        return back()->with('flash', [
            'success' => 'Данные растения обновлены',
        ]);
    }

    public function destroy(Plant $plant): RedirectResponse
    {
        $plant->delete();

        return back()->with('flash', [
            'success' => 'Растение удалено',
        ]);
    }

    private function preparePayload(array $input, ?Plant $plant = null): array
    {
        $payload = $input;
        $payload['slug'] = $input['slug']
            ?? $plant?->slug
            ?? Str::slug($input['name'].'-'.Str::random(4));

        $payload['environment_requirements'] = $this->sanitizeEnvironment(
            Arr::get($input, 'environment_requirements')
        );

        if (empty($payload['environment_requirements'])) {
            $payload['environment_requirements'] = null;
        }

        if (empty($payload['growth_phases'])) {
            $payload['growth_phases'] = null;
        }

        if (empty($payload['recommended_recipes'])) {
            $payload['recommended_recipes'] = null;
        }

        if (empty($payload['metadata'])) {
            $payload['metadata'] = null;
        }

        return $payload;
    }

    public function storePriceVersion(StorePlantPriceRequest $request, Plant $plant): RedirectResponse
    {
        $payload = $request->validated();
        $payload['currency'] = $payload['currency'] ?? 'RUB';
        $plant->priceVersions()->create($payload);

        return back()->with('flash', [
            'success' => 'Ценовая версия сохранена',
        ]);
    }

    public function taxonomies(): JsonResponse
    {
        return response()->json([
            'status' => 'ok',
            'data' => $this->loadTaxonomies(),
        ]);
    }

    public function updateTaxonomy(UpdatePlantTaxonomyRequest $request, string $taxonomy): JsonResponse
    {
        $taxonomies = $this->loadTaxonomies();
        $allowedKeys = array_keys($taxonomies);

        if (! in_array($taxonomy, $allowedKeys, true)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unknown taxonomy key',
            ], 422);
        }

        $items = collect($request->validated('items'))
            ->map(fn (array $item) => [
                'id' => $item['id'],
                'label' => $item['label'],
            ])
            ->values()
            ->all();

        $ids = array_column($items, 'id');
        if (count($ids) !== count(array_unique($ids))) {
            return response()->json([
                'status' => 'error',
                'message' => 'Duplicate taxonomy ids are not allowed',
            ], 422);
        }

        $taxonomies[$taxonomy] = $items;
        $this->saveTaxonomies($taxonomies);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'key' => $taxonomy,
                'items' => $taxonomies[$taxonomy],
            ],
        ]);
    }

    private function sanitizeEnvironment(mixed $value): ?array
    {
        if (! is_array($value)) {
            return null;
        }

        $normalized = [];
        foreach ($value as $metric => $range) {
            if (! is_array($range)) {
                continue;
            }

            $min = $this->nullableFloat($range['min'] ?? null);
            $max = $this->nullableFloat($range['max'] ?? null);

            if ($min === null && $max === null) {
                continue;
            }

            $normalized[$metric] = [
                'min' => $min,
                'max' => $max,
            ];
        }

        return empty($normalized) ? null : $normalized;
    }

    private function nullableFloat(mixed $value): ?float
    {
        if ($value === null || $value === '') {
            return null;
        }

        return is_numeric($value) ? (float) $value : null;
    }

    private function loadTaxonomies(): array
    {
        $path = $this->taxonomyPath();

        if (! File::exists($path)) {
            return [];
        }

        return json_decode(File::get($path), true) ?? [];
    }

    private function saveTaxonomies(array $taxonomies): void
    {
        File::put(
            $this->taxonomyPath(),
            json_encode($taxonomies, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE).PHP_EOL
        );
    }

    private function taxonomyPath(): string
    {
        return base_path('config/plant_taxonomies.json');
    }
}
