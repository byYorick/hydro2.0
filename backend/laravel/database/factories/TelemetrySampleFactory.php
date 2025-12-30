<?php

namespace Database\Factories;

use App\Models\TelemetrySample;
use App\Models\Sensor;
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
            'sensor_id' => Sensor::factory(),
            'zone_id' => function (array $attributes) {
                $sensorAttr = $attributes['sensor_id'] ?? null;
                if ($sensorAttr instanceof Sensor) {
                    return $sensorAttr->zone_id;
                }

                $sensor = $sensorAttr ? Sensor::find($sensorAttr) : null;
                return $sensor?->zone_id;
            },
            'cycle_id' => null,
            'value' => $this->faker->randomFloat(2, 0, 10),
            'quality' => 'GOOD',
            'metadata' => [],
            'ts' => Carbon::now(),
        ];
    }
}
