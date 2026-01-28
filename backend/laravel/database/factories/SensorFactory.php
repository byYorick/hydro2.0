<?php

namespace Database\Factories;

use App\Models\Greenhouse;
use App\Models\Sensor;
use App\Models\Zone;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\Sensor>
 */
class SensorFactory extends Factory
{
    protected $model = Sensor::class;

    public function definition(): array
    {
        return [
            'zone_id' => Zone::factory(),
            'greenhouse_id' => function (array $attributes) {
                $zoneAttr = $attributes['zone_id'] ?? null;
                if ($zoneAttr instanceof Zone) {
                    return $zoneAttr->greenhouse_id;
                }
                if ($zoneAttr) {
                    $zone = Zone::find($zoneAttr);
                    if ($zone) {
                        return $zone->greenhouse_id;
                    }
                }

                return Greenhouse::factory();
            },
            'node_id' => null,
            'scope' => 'inside',
            'type' => $this->faker->randomElement(['PH', 'EC', 'TEMPERATURE', 'HUMIDITY']),
            'label' => $this->faker->word(),
            'unit' => null,
            'specs' => null,
            'is_active' => true,
            'last_read_at' => null,
        ];
    }
}
