<?php

namespace App\Http\Controllers;

use App\Models\GrowCyclePhase;
use App\Models\NutrientProduct;
use App\Models\RecipeRevisionPhase;
use Illuminate\Database\QueryException;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Arr;
use Illuminate\Validation\ValidationException;
use Inertia\Inertia;
use Inertia\Response as InertiaResponse;
use Symfony\Component\HttpFoundation\Response;

class NutrientProductController extends Controller
{
    /**
     * Получить справочник продуктов питания (NPK / Calcium / Micro).
     */
    public function index(Request $request): JsonResponse
    {
        $validated = $request->validate([
            'component' => ['nullable', 'string', 'in:npk,calcium,magnesium,micro'],
        ]);

        $query = NutrientProduct::query()
            ->select([
                'id',
                'manufacturer',
                'name',
                'component',
                'composition',
                'recommended_stage',
                'notes',
                'metadata',
            ]);

        if (! empty($validated['component'])) {
            $query->where('component', $validated['component']);
        }

        $products = $query
            ->orderBy('component')
            ->orderBy('manufacturer')
            ->orderBy('name')
            ->get();

        return response()->json([
            'status' => 'ok',
            'data' => $products,
        ]);
    }

    /**
     * Получить один продукт питания.
     */
    public function show(NutrientProduct $nutrientProduct): JsonResponse
    {
        return response()->json([
            'status' => 'ok',
            'data' => $nutrientProduct,
        ]);
    }

    /**
     * Создать продукт питания.
     */
    public function store(Request $request): JsonResponse
    {
        $data = $request->validate([
            'manufacturer' => ['required', 'string', 'max:128'],
            'name' => ['required', 'string', 'max:191'],
            'component' => ['required', 'string', 'in:npk,calcium,magnesium,micro'],
            'composition' => ['nullable', 'string', 'max:128'],
            'recommended_stage' => ['nullable', 'string', 'max:64'],
            'notes' => ['nullable', 'string', 'max:5000'],
            'metadata' => ['nullable', 'array'],
        ]);

        $data['metadata'] = $this->normalizeMetadata($data);
        $this->validateUniqueProduct($data);

        $product = NutrientProduct::query()->create($data);

        return response()->json([
            'status' => 'ok',
            'data' => $product,
        ], Response::HTTP_CREATED);
    }

    /**
     * Обновить продукт питания.
     */
    public function update(Request $request, NutrientProduct $nutrientProduct): JsonResponse
    {
        $data = $request->validate([
            'manufacturer' => ['sometimes', 'required', 'string', 'max:128'],
            'name' => ['sometimes', 'required', 'string', 'max:191'],
            'component' => ['sometimes', 'required', 'string', 'in:npk,calcium,magnesium,micro'],
            'composition' => ['nullable', 'string', 'max:128'],
            'recommended_stage' => ['nullable', 'string', 'max:64'],
            'notes' => ['nullable', 'string', 'max:5000'],
            'metadata' => ['nullable', 'array'],
        ]);

        if (array_key_exists('metadata', $data)) {
            $data['metadata'] = $this->normalizeMetadata($data);
        }

        $this->validateUniqueProduct($data, $nutrientProduct->id, $nutrientProduct);
        $nutrientProduct->update($data);

        return response()->json([
            'status' => 'ok',
            'data' => $nutrientProduct->fresh(),
        ]);
    }

    /**
     * Удалить продукт питания.
     */
    public function destroy(NutrientProduct $nutrientProduct): JsonResponse
    {
        if ($this->isReferencedInPhases($nutrientProduct->id)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Невозможно удалить продукт: он используется в рецептах или циклах.',
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        try {
            $nutrientProduct->delete();
        } catch (QueryException $e) {
            return response()->json([
                'status' => 'error',
                'message' => 'Невозможно удалить продукт: он используется в рецептах или циклах.',
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        return response()->json([
            'status' => 'ok',
        ]);
    }

    /**
     * Inertia-страница списка удобрений.
     */
    public function indexPage(): InertiaResponse
    {
        $products = NutrientProduct::query()
            ->orderBy('component')
            ->orderBy('manufacturer')
            ->orderBy('name')
            ->get([
                'id',
                'manufacturer',
                'name',
                'component',
                'composition',
                'recommended_stage',
                'notes',
                'metadata',
                'created_at',
                'updated_at',
            ]);

        return Inertia::render('Nutrients/Index', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'nutrients' => $products,
        ]);
    }

    /**
     * Inertia-страница создания удобрения.
     */
    public function createPage(): InertiaResponse
    {
        return Inertia::render('Nutrients/Edit', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'nutrient' => null,
        ]);
    }

    /**
     * Inertia-страница редактирования удобрения.
     */
    public function editPage(NutrientProduct $nutrientProduct): InertiaResponse
    {
        return Inertia::render('Nutrients/Edit', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'nutrient' => $nutrientProduct->only([
                'id',
                'manufacturer',
                'name',
                'component',
                'composition',
                'recommended_stage',
                'notes',
                'metadata',
                'created_at',
                'updated_at',
            ]),
        ]);
    }

    private function normalizeMetadata(array $data): ?array
    {
        $metadata = Arr::get($data, 'metadata');
        if (! is_array($metadata)) {
            return null;
        }

        $clean = array_filter($metadata, fn ($value) => $value !== null && $value !== '');

        return empty($clean) ? null : $clean;
    }

    private function validateUniqueProduct(
        array $data,
        ?int $ignoreId = null,
        ?NutrientProduct $existing = null
    ): void
    {
        $manufacturer = Arr::get($data, 'manufacturer', $existing?->manufacturer);
        $name = Arr::get($data, 'name', $existing?->name);
        $component = Arr::get($data, 'component', $existing?->component);

        if ($manufacturer === null || $name === null || $component === null) {
            return;
        }

        $alreadyExists = NutrientProduct::query()
            ->where('manufacturer', $manufacturer)
            ->where('name', $name)
            ->where('component', $component)
            ->when($ignoreId !== null, fn ($query) => $query->whereKeyNot($ignoreId))
            ->exists();

        if ($alreadyExists) {
            throw ValidationException::withMessages([
                'unique_key' => ['Продукт с таким производителем, названием и компонентом уже существует.'],
            ]);
        }
    }

    private function isReferencedInPhases(int $productId): bool
    {
        $isReferencedInRecipePhases = RecipeRevisionPhase::query()
            ->where('nutrient_npk_product_id', $productId)
            ->orWhere('nutrient_calcium_product_id', $productId)
            ->orWhere('nutrient_magnesium_product_id', $productId)
            ->orWhere('nutrient_micro_product_id', $productId)
            ->exists();

        if ($isReferencedInRecipePhases) {
            return true;
        }

        return GrowCyclePhase::query()
            ->where('nutrient_npk_product_id', $productId)
            ->orWhere('nutrient_calcium_product_id', $productId)
            ->orWhere('nutrient_magnesium_product_id', $productId)
            ->orWhere('nutrient_micro_product_id', $productId)
            ->exists();
    }
}
