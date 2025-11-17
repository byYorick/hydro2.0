<?php

namespace App\Http\Controllers;

use App\Models\Preset;
use App\Services\PresetService;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class PresetController extends Controller
{
    public function __construct(
        private PresetService $presetService
    ) {
    }

    public function index()
    {
        $items = Preset::query()
            ->with('defaultRecipe')
            ->latest('id')
            ->paginate(25);
        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function store(Request $request)
    {
        $data = $request->validate([
            'name' => ['required', 'string', 'max:255'],
            'plant_type' => ['required', 'string', 'max:255'],
            'ph_optimal_range' => ['nullable', 'array'],
            'ec_range' => ['nullable', 'array'],
            'vpd_range' => ['nullable', 'array'],
            'light_intensity_range' => ['nullable', 'array'],
            'climate_ranges' => ['nullable', 'array'],
            'irrigation_behavior' => ['nullable', 'array'],
            'growth_profile' => ['nullable', 'string', 'in:fast,mid,slow'],
            'default_recipe_id' => ['nullable', 'integer', 'exists:recipes,id'],
            'description' => ['nullable', 'string'],
        ]);

        $preset = $this->presetService->create($data);
        return response()->json(['status' => 'ok', 'data' => $preset], Response::HTTP_CREATED);
    }

    public function show(Preset $preset)
    {
        $preset->load('defaultRecipe');
        return response()->json(['status' => 'ok', 'data' => $preset]);
    }

    public function update(Request $request, Preset $preset)
    {
        $data = $request->validate([
            'name' => ['sometimes', 'string', 'max:255'],
            'plant_type' => ['sometimes', 'string', 'max:255'],
            'ph_optimal_range' => ['nullable', 'array'],
            'ec_range' => ['nullable', 'array'],
            'vpd_range' => ['nullable', 'array'],
            'light_intensity_range' => ['nullable', 'array'],
            'climate_ranges' => ['nullable', 'array'],
            'irrigation_behavior' => ['nullable', 'array'],
            'growth_profile' => ['nullable', 'string', 'in:fast,mid,slow'],
            'default_recipe_id' => ['nullable', 'integer', 'exists:recipes,id'],
            'description' => ['nullable', 'string'],
        ]);
        $preset = $this->presetService->update($preset, $data);
        return response()->json(['status' => 'ok', 'data' => $preset]);
    }

    public function destroy(Preset $preset)
    {
        try {
            $this->presetService->delete($preset);
            return response()->json(['status' => 'ok']);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }
}

