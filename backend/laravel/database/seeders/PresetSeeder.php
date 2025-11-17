<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;
use App\Models\Preset;

class PresetSeeder extends Seeder
{
    public function run(): void
    {
        // Листовые культуры (салат)
        Preset::firstOrCreate(
            ['name' => 'Lettuce Standard'],
            [
                'plant_type' => 'lettuce',
                'ph_optimal_range' => ['min' => 5.5, 'max' => 6.5],
                'ec_range' => ['min' => 1.2, 'max' => 1.8],
                'vpd_range' => ['min' => 0.8, 'max' => 1.2],
                'light_intensity_range' => ['min' => 200, 'max' => 400],
                'climate_ranges' => [
                    'temp_day' => ['min' => 20, 'max' => 24],
                    'temp_night' => ['min' => 18, 'max' => 20],
                    'humidity_day' => ['min' => 55, 'max' => 65],
                    'humidity_night' => ['min' => 60, 'max' => 70],
                ],
                'irrigation_behavior' => [
                    'interval_sec' => 900,
                    'duration_sec' => 8,
                    'adaptive' => true,
                ],
                'growth_profile' => 'mid',
                'description' => 'Standard lettuce growing preset',
            ]
        );

        // Руккола
        Preset::firstOrCreate(
            ['name' => 'Arugula'],
            [
                'plant_type' => 'arugula',
                'ph_optimal_range' => ['min' => 6.0, 'max' => 7.0],
                'ec_range' => ['min' => 1.0, 'max' => 1.6],
                'vpd_range' => ['min' => 0.8, 'max' => 1.2],
                'light_intensity_range' => ['min' => 250, 'max' => 450],
                'climate_ranges' => [
                    'temp_day' => ['min' => 18, 'max' => 22],
                    'temp_night' => ['min' => 15, 'max' => 18],
                    'humidity_day' => ['min' => 50, 'max' => 60],
                    'humidity_night' => ['min' => 55, 'max' => 65],
                ],
                'irrigation_behavior' => [
                    'interval_sec' => 720,
                    'duration_sec' => 6,
                    'adaptive' => true,
                ],
                'growth_profile' => 'fast',
                'description' => 'Arugula growing preset',
            ]
        );

        // Томат/огурец
        Preset::firstOrCreate(
            ['name' => 'Tomato/Cucumber'],
            [
                'plant_type' => 'tomato',
                'ph_optimal_range' => ['min' => 5.5, 'max' => 6.5],
                'ec_range' => ['min' => 2.0, 'max' => 3.5],
                'vpd_range' => ['min' => 0.8, 'max' => 1.2],
                'light_intensity_range' => ['min' => 400, 'max' => 600],
                'climate_ranges' => [
                    'temp_day' => ['min' => 22, 'max' => 26],
                    'temp_night' => ['min' => 18, 'max' => 22],
                    'humidity_day' => ['min' => 60, 'max' => 70],
                    'humidity_night' => ['min' => 65, 'max' => 75],
                ],
                'irrigation_behavior' => [
                    'interval_sec' => 1800,
                    'duration_sec' => 15,
                    'adaptive' => true,
                ],
                'growth_profile' => 'slow',
                'description' => 'Tomato and cucumber growing preset',
            ]
        );

        // Микрозелень
        Preset::firstOrCreate(
            ['name' => 'Microgreens'],
            [
                'plant_type' => 'microgreens',
                'ph_optimal_range' => ['min' => 5.8, 'max' => 6.2],
                'ec_range' => ['min' => 0.8, 'max' => 1.2],
                'vpd_range' => ['min' => 0.7, 'max' => 1.0],
                'light_intensity_range' => ['min' => 150, 'max' => 300],
                'climate_ranges' => [
                    'temp_day' => ['min' => 18, 'max' => 22],
                    'temp_night' => ['min' => 16, 'max' => 20],
                    'humidity_day' => ['min' => 50, 'max' => 60],
                    'humidity_night' => ['min' => 55, 'max' => 65],
                ],
                'irrigation_behavior' => [
                    'interval_sec' => 360,
                    'duration_sec' => 4,
                    'adaptive' => false,
                ],
                'growth_profile' => 'fast',
                'description' => 'Microgreens growing preset',
            ]
        );

        // Базилик/зелень
        Preset::firstOrCreate(
            ['name' => 'Basil/Herbs'],
            [
                'plant_type' => 'basil',
                'ph_optimal_range' => ['min' => 5.8, 'max' => 6.5],
                'ec_range' => ['min' => 1.0, 'max' => 1.6],
                'vpd_range' => ['min' => 0.8, 'max' => 1.2],
                'light_intensity_range' => ['min' => 300, 'max' => 500],
                'climate_ranges' => [
                    'temp_day' => ['min' => 22, 'max' => 26],
                    'temp_night' => ['min' => 18, 'max' => 22],
                    'humidity_day' => ['min' => 55, 'max' => 65],
                    'humidity_night' => ['min' => 60, 'max' => 70],
                ],
                'irrigation_behavior' => [
                    'interval_sec' => 1080,
                    'duration_sec' => 10,
                    'adaptive' => true,
                ],
                'growth_profile' => 'mid',
                'description' => 'Basil and herbs growing preset',
            ]
        );

        // Клубника
        Preset::firstOrCreate(
            ['name' => 'Strawberry'],
            [
                'plant_type' => 'strawberry',
                'ph_optimal_range' => ['min' => 5.5, 'max' => 6.5],
                'ec_range' => ['min' => 1.4, 'max' => 2.2],
                'vpd_range' => ['min' => 0.8, 'max' => 1.2],
                'light_intensity_range' => ['min' => 300, 'max' => 500],
                'climate_ranges' => [
                    'temp_day' => ['min' => 20, 'max' => 24],
                    'temp_night' => ['min' => 16, 'max' => 18],
                    'humidity_day' => ['min' => 60, 'max' => 70],
                    'humidity_night' => ['min' => 65, 'max' => 75],
                ],
                'irrigation_behavior' => [
                    'interval_sec' => 1200,
                    'duration_sec' => 12,
                    'adaptive' => true,
                ],
                'growth_profile' => 'mid',
                'description' => 'Strawberry growing preset',
            ]
        );
    }
}

