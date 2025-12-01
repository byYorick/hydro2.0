<?php

namespace Database\Seeders;

use App\Models\Plant;
use Illuminate\Database\Seeder;
use Illuminate\Support\Arr;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Str;

class PlantTaxonomySeeder extends Seeder
{
    /**
     * Run the database seeds.
     */
    public function run(): void
    {
        $taxonomyPath = base_path('../configs/plant_taxonomies.json');
        $taxonomies = [];

        if (File::exists($taxonomyPath)) {
            $taxonomies = json_decode(File::get($taxonomyPath), true) ?? [];
        }

        $substrateDefault = Arr::get($taxonomies, 'substrate_type.0.id', 'coco');
        $systemDefault = Arr::get($taxonomies, 'growing_system.0.id', 'nft');
        $photoperiodDefault = Arr::get($taxonomies, 'photoperiod_preset.1.id', '16_8');

        $plants = [
            [
                'slug' => 'basil-genovese',
                'name' => 'Базилик (Генуэзский)',
                'species' => 'Ocimum basilicum',
                'substrate_type' => $substrateDefault,
                'growing_system' => $systemDefault,
                'photoperiod_preset' => $photoperiodDefault,
                'seasonality' => 'all_year',
                'environment_requirements' => [
                    'temperature' => ['min' => 20, 'max' => 27],
                    'humidity' => ['min' => 55, 'max' => 70],
                    'ph' => ['min' => 5.5, 'max' => 6.5],
                    'ec' => ['min' => 1.2, 'max' => 1.6],
                ],
                'growth_phases' => [
                    ['name' => 'Рассада', 'duration_days' => 14],
                    ['name' => 'Вегетация', 'duration_days' => 21],
                    ['name' => 'Сбор урожая', 'duration_days' => 7],
                ],
            ],
            [
                'slug' => 'tomato-cherry',
                'name' => 'Томат (Черри)',
                'species' => 'Solanum lycopersicum',
                'variety' => 'Cherry',
                'substrate_type' => 'rockwool',
                'growing_system' => 'drip',
                'photoperiod_preset' => '18_6',
                'seasonality' => 'multi_cycle',
                'environment_requirements' => [
                    'temperature' => ['min' => 18, 'max' => 26],
                    'humidity' => ['min' => 60, 'max' => 75],
                    'ph' => ['min' => 5.8, 'max' => 6.5],
                    'ec' => ['min' => 2.0, 'max' => 3.5],
                ],
                'growth_phases' => [
                    ['name' => 'Рассада', 'duration_days' => 21],
                    ['name' => 'Вегетация', 'duration_days' => 28],
                    ['name' => 'Цветение', 'duration_days' => 21],
                    ['name' => 'Плодоношение', 'duration_days' => 30],
                ],
            ],
        ];

        foreach ($plants as $plant) {
            $slug = $plant['slug'] ?? Str::slug($plant['name'].'-'.($plant['variety'] ?? ''));
            $model = Plant::updateOrCreate(
                ['slug' => $slug],
                $plant
            );

            $model->priceVersions()->firstOrCreate(
                ['effective_from' => now()->startOfMonth()],
                [
                    'currency' => 'RUB',
                    'seedling_cost' => 15.0,
                    'substrate_cost' => 8.5,
                    'nutrient_cost' => 4.2,
                    'labor_cost' => 6.0,
                    'wholesale_price' => 55.0,
                    'retail_price' => 85.0,
                    'source' => 'seed',
                ]
            );
        }
    }
}
