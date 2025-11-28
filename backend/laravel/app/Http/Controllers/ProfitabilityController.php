<?php

namespace App\Http\Controllers;

use App\Models\Plant;
use App\Services\Profitability\ProfitabilityCalculator;
use Carbon\Carbon;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ProfitabilityController extends Controller
{
    public function __construct(private readonly ProfitabilityCalculator $profitability)
    {
    }

    public function calculate(Request $request): JsonResponse
    {
        $data = $request->validate([
            'plant_ids' => ['required', 'array'],
            'plant_ids.*' => ['integer', 'exists:plants,id'],
            'date' => ['nullable', 'date'],
        ]);

        $at = isset($data['date']) ? Carbon::parse($data['date']) : null;

        $results = Plant::query()
            ->whereIn('id', $data['plant_ids'])
            ->get()
            ->map(fn (Plant $plant) => $this->profitability->calculatePlant($plant, $at))
            ->values();

        return response()->json([
            'status' => 'ok',
            'data' => $results,
        ], 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }

    public function plant(Request $request, Plant $plant): JsonResponse
    {
        $request->validate([
            'date' => ['nullable', 'date'],
        ]);

        $at = $request->filled('date') ? Carbon::parse($request->input('date')) : null;

        return response()->json([
            'status' => 'ok',
            'data' => $this->profitability->calculatePlant($plant, $at),
        ], 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }
}
