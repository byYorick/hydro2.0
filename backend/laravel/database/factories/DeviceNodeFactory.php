<?php

namespace Database\Factories;

use App\Models\DeviceNode;
use App\Models\Zone;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\DeviceNode>
 */
class DeviceNodeFactory extends Factory
{
    protected $model = DeviceNode::class;

    public function definition(): array
    {
        return [
            'uid' => 'nd-'.$this->faker->unique()->bothify('???-###'),
            'name' => $this->faker->word().' Node',
            'type' => $this->faker->randomElement(['ph', 'ec', 'climate', 'irrigation', 'lighting']),
            'fw_version' => $this->faker->semver(),
            'status' => $this->faker->randomElement(['online', 'offline', 'error']),
            'zone_id' => null,
            'config' => [],
        ];
    }
}

