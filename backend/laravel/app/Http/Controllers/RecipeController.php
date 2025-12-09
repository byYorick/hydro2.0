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
    ) {
    }

    public function index(Request $request): JsonResponse
    {
        // Валидация query параметров
        $validated = $request->validate([
            'search' => ['nullable', 'string', 'max:255'],
        ]);
        
        $query = Recipe::query()->with('phases');
        
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
        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function store(Request $request): JsonResponse
    {
        $data = $request->validate([
            'name' => ['required', 'string', 'max:255'],
            'description' => ['nullable', 'string'],
        ]);

        $recipe = $this->recipeService->create($data);
        return response()->json(['status' => 'ok', 'data' => $recipe], Response::HTTP_CREATED);
    }

    public function show(Recipe $recipe): JsonResponse
    {
        $recipe->load('phases');
        return response()->json(['status' => 'ok', 'data' => $recipe]);
    }

    public function update(Request $request, Recipe $recipe): JsonResponse
    {
        $data = $request->validate([
            'name' => ['sometimes', 'string', 'max:255'],
            'description' => ['nullable', 'string'],
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


