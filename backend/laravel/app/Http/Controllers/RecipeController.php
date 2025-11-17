<?php

namespace App\Http\Controllers;

use App\Models\Recipe;
use App\Services\RecipeService;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class RecipeController extends Controller
{
    public function __construct(
        private RecipeService $recipeService
    ) {
    }

    public function index()
    {
        $items = Recipe::query()->with('phases')->latest('id')->paginate(25);
        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function store(Request $request)
    {
        $data = $request->validate([
            'name' => ['required', 'string', 'max:255'],
            'description' => ['nullable', 'string'],
        ]);

        $recipe = $this->recipeService->create($data);
        return response()->json(['status' => 'ok', 'data' => $recipe], Response::HTTP_CREATED);
    }

    public function show(Recipe $recipe)
    {
        $recipe->load('phases');
        return response()->json(['status' => 'ok', 'data' => $recipe]);
    }

    public function update(Request $request, Recipe $recipe)
    {
        $data = $request->validate([
            'name' => ['sometimes', 'string', 'max:255'],
            'description' => ['nullable', 'string'],
        ]);
        $recipe = $this->recipeService->update($recipe, $data);
        return response()->json(['status' => 'ok', 'data' => $recipe]);
    }

    public function destroy(Recipe $recipe)
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


