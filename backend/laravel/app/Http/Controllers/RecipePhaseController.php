<?php

namespace App\Http\Controllers;

use App\Models\RecipePhase;
use App\Models\Recipe;
use App\Services\RecipeService;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class RecipePhaseController extends Controller
{
    public function __construct(
        private RecipeService $recipeService
    ) {
    }

    public function store(Request $request, Recipe $recipe)
    {
        $data = $request->validate([
            'phase_index' => ['required', 'integer', 'min:0'],
            'name' => ['required', 'string', 'max:255'],
            'duration_hours' => ['required', 'integer', 'min:1'],
            'targets' => ['required', 'array'],
            'targets.ph' => ['nullable', 'numeric', 'between:0,14'],
            'targets.ec' => ['nullable', 'numeric', 'min:0'],
            'targets.temp_air' => ['nullable', 'numeric'],
            'targets.humidity_air' => ['nullable', 'numeric', 'between:0,100'],
            'targets.light_hours' => ['nullable', 'integer', 'between:0,24'],
            'targets.irrigation_interval_sec' => ['nullable', 'integer', 'min:1'],
            'targets.irrigation_duration_sec' => ['nullable', 'integer', 'min:1'],
        ]);
        $phase = $this->recipeService->addPhase($recipe, $data);
        return response()->json(['status' => 'ok', 'data' => $phase], Response::HTTP_CREATED);
    }

    public function update(Request $request, RecipePhase $recipePhase)
    {
        $data = $request->validate([
            'phase_index' => ['sometimes', 'integer', 'min:0'],
            'name' => ['sometimes', 'string', 'max:255'],
            'duration_hours' => ['sometimes', 'integer', 'min:1'],
            'targets' => ['sometimes', 'array'],
            'targets.ph' => ['nullable', 'numeric', 'between:0,14'],
            'targets.ec' => ['nullable', 'numeric', 'min:0'],
            'targets.temp_air' => ['nullable', 'numeric'],
            'targets.humidity_air' => ['nullable', 'numeric', 'between:0,100'],
            'targets.light_hours' => ['nullable', 'integer', 'between:0,24'],
            'targets.irrigation_interval_sec' => ['nullable', 'integer', 'min:1'],
            'targets.irrigation_duration_sec' => ['nullable', 'integer', 'min:1'],
        ]);
        $phase = $this->recipeService->updatePhase($recipePhase, $data);
        return response()->json(['status' => 'ok', 'data' => $phase]);
    }

    public function destroy(RecipePhase $recipePhase)
    {
        $this->recipeService->deletePhase($recipePhase);
        return response()->json(['status' => 'ok']);
    }
}


