<?php

namespace Database\Factories;

use App\Models\GrowStageTemplate;
use Illuminate\Database\Eloquent\Factories\Factory;

class GrowStageTemplateFactory extends Factory
{
    protected $model = GrowStageTemplate::class;

    public function definition(): array
    {
        $codes = ['PLANTING', 'ROOTING', 'VEG', 'FLOWER', 'FRUIT', 'HARVEST'];
        $names = ['Посадка', 'Укоренение', 'Вега', 'Цветение', 'Плодоношение', 'Сбор'];
        $icons = ['🌱', '🌿', '🌳', '🌸', '🍅', '✂️'];
        $colors = ['#10b981', '#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6'];

        $index = $this->faker->numberBetween(0, count($codes) - 1);
        $suffix = strtoupper($this->faker->unique()->lexify('????'));

        return [
            'name' => $names[$index].' '.$suffix,
            'code' => $codes[$index].'_'.$suffix,
            'order_index' => $index,
            'default_duration_days' => $this->faker->numberBetween(1, 30),
            'ui_meta' => [
                'color' => $colors[$index],
                'icon' => $icons[$index],
                'description' => $names[$index].' '.$suffix,
            ],
        ];
    }

    public function planting(): static
    {
        return $this->state(fn (array $attributes) => [
            'name' => 'Посадка',
            'code' => 'PLANTING',
            'order_index' => 0,
            'default_duration_days' => 1,
        ]);
    }

    public function veg(): static
    {
        return $this->state(fn (array $attributes) => [
            'name' => 'Вега',
            'code' => 'VEG',
            'order_index' => 2,
            'default_duration_days' => 21,
        ]);
    }

    public function flower(): static
    {
        return $this->state(fn (array $attributes) => [
            'name' => 'Цветение',
            'code' => 'FLOWER',
            'order_index' => 3,
            'default_duration_days' => 14,
        ]);
    }
}
