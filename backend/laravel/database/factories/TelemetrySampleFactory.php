<?php

namespace Database\Factories;

use App\Models\TelemetrySample;
use App\Models\Zone;
use App\Models\DeviceNode;
use Illuminate\Database\Eloquent\Factories\Factory;
use Carbon\Carbon;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\TelemetrySample>
 */
class TelemetrySampleFactory extends Factory
{
    protected $model = TelemetrySample::class;

    public function definition(): array
    {
        return [
            'zone_id' => Zone::factory(),
            'node_id' => DeviceNode::factory(),
            'channel' => $this->faker->word(),
            'metric_type' => $this->faker->randomElement(['ph', 'ec', 'temp_air', 'temp_water', 'humidity_air']),
            'value' => $this->faker->randomFloat(2, 0, 10),
            'raw' => null,
            'ts' => Carbon::now(),
        ];
    }
}
