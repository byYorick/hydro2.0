<?php

namespace App\Http\Controllers;

use App\Http\Requests\StorePlantPriceRequest;
use App\Http\Requests\StorePlantRequest;
use App\Http\Requests\UpdatePlantRequest;
use App\Models\Plant;
use App\Services\Profitability\ProfitabilityCalculator;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Arr;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Str;
use Inertia\Inertia;
use Inertia\Response;

class PlantController extends Controller
{
    public function __construct(private readonly ProfitabilityCalculator $profitability)
    {
    }

    public function index(Request $request): Response
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

        return Inertia::render('Plants/Index', [
            'plants' => $plants,
            'taxonomies' => $this->loadTaxonomies(),
        ]);
    }

    public function store(StorePlantRequest $request): RedirectResponse
    {
        $payload = $this->preparePayload($request->validated());
        Plant::create($payload);

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
        $path = base_path('../configs/plant_taxonomies.json');

        if (! File::exists($path)) {
            return [];
        }

        return json_decode(File::get($path), true) ?? [];
    }
}
