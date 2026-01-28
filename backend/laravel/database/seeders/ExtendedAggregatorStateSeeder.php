<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;

/**
 * Сидер для состояния агрегатора телеметрии
 */
class ExtendedAggregatorStateSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Инициализация состояния агрегатора ===');

        $aggregationTypes = ['1m', '1h', 'daily'];

        foreach ($aggregationTypes as $type) {
            $exists = DB::table('aggregator_state')
                ->where('aggregation_type', $type)
                ->exists();

            if ($exists) {
                continue;
            }

            // Устанавливаем последнюю временную метку на 7 дней назад для начала агрегации
            DB::table('aggregator_state')->insert([
                'aggregation_type' => $type,
                'last_ts' => now()->subDays(7),
                'updated_at' => now(),
            ]);
        }

        $this->command->info("Инициализировано типов агрегации: " . count($aggregationTypes));
        $this->command->info("Всего записей состояния: " . DB::table('aggregator_state')->count());
    }
}

