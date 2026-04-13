<?php

namespace App\Http\Controllers;

use App\Http\Requests\SubstrateRequest;
use App\Models\Substrate;
use Illuminate\Http\JsonResponse;
use Symfony\Component\HttpFoundation\Response;

class SubstrateController extends Controller
{
    public function index(): JsonResponse
    {
        $items = Substrate::query()->orderBy('name')->get();

        return response()->json([
            'status' => 'ok',
            'data' => $items,
        ]);
    }

    public function show(Substrate $substrate): JsonResponse
    {
        return response()->json([
            'status' => 'ok',
            'data' => $substrate,
        ]);
    }

    public function store(SubstrateRequest $request): JsonResponse
    {
        $substrate = Substrate::create($request->validated());

        return response()->json([
            'status' => 'ok',
            'data' => $substrate,
        ], Response::HTTP_CREATED);
    }

    public function update(SubstrateRequest $request, Substrate $substrate): JsonResponse
    {
        $substrate->update($request->validated());

        return response()->json([
            'status' => 'ok',
            'data' => $substrate->fresh(),
        ]);
    }

    public function destroy(Substrate $substrate): JsonResponse
    {
        $substrate->delete();

        return response()->json([
            'status' => 'ok',
            'message' => 'Substrate deleted',
        ]);
    }
}
