<?php

namespace App\Services\Profitability;

use App\Models\Plant;
use App\Models\PlantPriceVersion;
use Carbon\Carbon;

class ProfitabilityCalculator
{
    public function calculatePlant(Plant $plant, ?Carbon $atDate = null): array
    {
        $priceVersion = $this->resolvePriceVersion($plant, $atDate);

        if (! $priceVersion) {
            return [
                'plant_id' => $plant->id,
                'currency' => 'RUB',
                'total_cost' => null,
                'wholesale_price' => null,
                'retail_price' => null,
                'margin_wholesale' => null,
                'margin_retail' => null,
                'has_pricing' => false,
            ];
        }

        $cost = $this->sumCosts($priceVersion);
        $wholesale = $priceVersion->wholesale_price ?? $this->resolveSalePrice($plant, 'wholesale', $priceVersion);
        $retail = $priceVersion->retail_price ?? $this->resolveSalePrice($plant, 'retail', $priceVersion);
        $hasPricing = $cost !== null || $wholesale !== null || $retail !== null;

        return [
            'plant_id' => $plant->id,
            'currency' => $priceVersion->currency,
            'total_cost' => $cost,
            'wholesale_price' => $wholesale,
            'retail_price' => $retail,
            'margin_wholesale' => $wholesale !== null && $cost !== null ? $wholesale - $cost : null,
            'margin_retail' => $retail !== null && $cost !== null ? $retail - $cost : null,
            'has_pricing' => $hasPricing,
            'price_version_id' => $priceVersion->id,
            'effective_from' => optional($priceVersion->effective_from)->toDateString(),
        ];
    }

    protected function resolvePriceVersion(Plant $plant, ?Carbon $atDate): ?PlantPriceVersion
    {
        $query = $plant->priceVersions()->newQuery();

        if ($atDate) {
            $query->where(function ($builder) use ($atDate) {
                $builder
                    ->whereNull('effective_from')
                    ->orWhere('effective_from', '<=', $atDate->toDateString());
            })
            ->where(function ($builder) use ($atDate) {
                $builder
                    ->whereNull('effective_to')
                    ->orWhere('effective_to', '>=', $atDate->toDateString());
            });
        }

        return $query
            ->orderByDesc('effective_from')
            ->orderByDesc('id')
            ->first();
    }

    protected function sumCosts(PlantPriceVersion $priceVersion): ?float
    {
        $baseCosts = collect([
            $priceVersion->seedling_cost,
            $priceVersion->substrate_cost,
            $priceVersion->nutrient_cost,
            $priceVersion->labor_cost,
            $priceVersion->protection_cost,
            $priceVersion->logistics_cost,
            $priceVersion->other_cost,
        ])->filter(fn ($value) => $value !== null)->sum();

        $versionItems = $priceVersion->relationLoaded('costItems')
            ? $priceVersion->costItems
            : $priceVersion->costItems()->get();

        $additionalPlantItems = $priceVersion->plant->relationLoaded('costItems')
            ? $priceVersion->plant->costItems
            : $priceVersion->plant->costItems()->get();

        $additionalCosts = $versionItems->sum('amount')
            + $additionalPlantItems
                ->whereNull('plant_price_version_id')
                ->sum('amount');

        $total = $baseCosts + $additionalCosts;

        if ($total === 0.0) {
            return null;
        }

        return round($total, 2);
    }

    protected function resolveSalePrice(Plant $plant, string $channel, PlantPriceVersion $version): ?float
    {
        $directCollection = $version->relationLoaded('salePrices')
            ? $version->salePrices
            : $version->salePrices()->get();

        $direct = $directCollection
            ->where('channel', $channel)
            ->where('is_active', true)
            ->sortByDesc('created_at')
            ->pluck('price')
            ->first();

        if ($direct !== null) {
            return (float) $direct;
        }

        $plantSales = $plant->relationLoaded('salePrices')
            ? $plant->salePrices
            : $plant->salePrices()->get();

        $fallback = $plantSales
            ->where('channel', $channel)
            ->where('is_active', true)
            ->sortByDesc('created_at')
            ->pluck('price')
            ->first();

        return $fallback !== null ? (float) $fallback : null;
    }
}

