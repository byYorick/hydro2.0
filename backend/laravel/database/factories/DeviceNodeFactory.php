<?php

namespace Database\Factories;

use App\Models\DeviceNode;
use Illuminate\Database\Eloquent\Factories\Factory;
use Illuminate\Support\Arr;
use Illuminate\Support\Str;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\DeviceNode>
 */
class DeviceNodeFactory extends Factory
{
    protected $model = DeviceNode::class;

    public function definition(): array
    {
        return [
            'uid' => sprintf(
                'nd-%s-%03d',
                Str::lower(Str::random(3)),
                $this->faker->unique()->numberBetween(0, 999)
            ),
            'name' => 'Node '.Str::upper(Str::random(4)),
            'type' => Arr::random(['ph', 'ec', 'climate', 'irrig', 'light', 'relay', 'water_sensor', 'recirculation']),
            'fw_version' => sprintf('1.%d.%d', random_int(0, 9), random_int(0, 9)),
            'status' => Arr::random(['online', 'offline', 'error']),
            'zone_id' => null,
            'config' => [],
        ];
    }
}
