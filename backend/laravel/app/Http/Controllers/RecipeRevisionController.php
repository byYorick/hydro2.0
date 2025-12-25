<?php

namespace App\Http\Controllers;

use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Services\RecipeRevisionService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Gate;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

class RecipeRevisionController extends Controller
{
    public function __construct(
        private RecipeRevisionService $recipeRevisionService
    ) {
    }

    /**
     * Получить ревизию рецепта с фазами
     * GET /api/recipe-revisions/{recipeRevision}
     */
    public function show(RecipeRevision $recipeRevision): JsonResponse
    {
        $recipeRevision->load([
            'phases.stageTemplate',
            'recipe',
            'creator',
        ]);

        return response()->json([
            'status' => 'ok',
            'data' => $recipeRevision,
        ]);
    }

    /**
     * Создать новую ревизию на основе существующей (clone)
     * POST /api/recipes/{recipe}/revisions
     */
    public function store(Request $request, Recipe $recipe): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверка прав: только агроном может создавать ревизии
        if (!Gate::allows('create', RecipeRevision::class)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Only agronomists can create recipe revisions',
            ], 403);
        }

        $data = $request->validate([
            'clone_from_revision_id' => ['nullable', 'integer', 'exists:recipe_revisions,id'],
            'description' => ['nullable', 'string'],
        ]);

        try {
            $revision = $this->recipeRevisionService->createRevision(
                $recipe,
                $data['clone_from_revision_id'] ?? null,
                $data['description'] ?? null,
                $user->id
            );

            return response()->json([
                'status' => 'ok',
                'data' => $revision,
            ], Response::HTTP_CREATED);
        } catch (\Exception $e) {
            Log::error('Failed to create recipe revision', [
                'recipe_id' => $recipe->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Редактировать черновик ревизии
     * PATCH /api/recipe-revisions/{recipeRevision}
     */
    public function update(Request $request, RecipeRevision $recipeRevision): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверка прав: только агроном может редактировать ревизии
        // Policy также проверяет статус DRAFT
        if (!Gate::allows('update', $recipeRevision)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Only agronomists can edit recipe revisions, and only DRAFT revisions can be edited',
            ], 403);
        }

        $data = $request->validate([
            'description' => ['nullable', 'string'],
        ]);

        try {
            $revision = $this->recipeRevisionService->updateRevision($recipeRevision, $data);

            return response()->json([
                'status' => 'ok',
                'data' => $revision,
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        } catch (\Exception $e) {
            Log::error('Failed to update recipe revision', [
                'revision_id' => $recipeRevision->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Опубликовать ревизию (lock)
     * POST /api/recipe-revisions/{recipeRevision}/publish
     */
    public function publish(Request $request, RecipeRevision $recipeRevision): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверка прав: только агроном может публиковать ревизии
        if (!Gate::allows('publish', $recipeRevision)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Only agronomists can publish recipe revisions',
            ], 403);
        }

        try {
            $revision = $this->recipeRevisionService->publishRevision($recipeRevision);

            return response()->json([
                'status' => 'ok',
                'data' => $revision,
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        } catch (\Exception $e) {
            Log::error('Failed to publish recipe revision', [
                'revision_id' => $recipeRevision->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }
}

