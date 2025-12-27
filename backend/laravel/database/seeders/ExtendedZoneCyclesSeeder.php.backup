<?php

namespace Database\Seeders;

use App\Models\Zone;
use App\Models\ZoneCycle;
use Illuminate\Database\Seeder;

/**
 * Сидер для циклов зон
 */
class ExtendedZoneCyclesSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание циклов зон ===');

        $zones = Zone::all();
        if ($zones->isEmpty()) {
            $this->command->warn('Зоны не найдены.');
            return;
        }

        $created = 0;

        foreach ($zones as $zone) {
            $created += $this->seedCyclesForZone($zone);
        }

        $this->command->info("Создано циклов: {$created}");
        $this->command->info("Всего циклов: " . ZoneCycle::count());
    }

    private function seedCyclesForZone(Zone $zone): int
    {
        $created = 0;

        // Создаем циклы в зависимости от статуса зоны
        $cycleCount = match ($zone->status) {
            'RUNNING' => rand(1, 3),
            'PAUSED' => rand(0, 2),
            'STOPPED' => rand(0, 1),
            default => 0,
        };

        $cycleTypes = ['GROWTH_CYCLE', 'MAINTENANCE_CYCLE', 'CLEANING_CYCLE'];
        $statuses = ['active', 'finished', 'aborted'];

        for ($i = 0; $i < $cycleCount; $i++) {
            $cycleType = $cycleTypes[rand(0, count($cycleTypes) - 1)];
            $status = $statuses[rand(0, count($statuses) - 1)];

            $startedAt = now()->subDays(rand(1, 60));
            $endsAt = match ($status) {
                'finished' => $startedAt->copy()->addDays(rand(1, 30)),
                'aborted' => $startedAt->copy()->addDays(rand(1, 10)),
                'active' => now()->addDays(rand(1, 30)),
                default => null,
            };

            ZoneCycle::create([
                'zone_id' => $zone->id,
                'type' => $cycleType,
                'status' => $status,
                'subsystems' => $this->generateSubsystems($cycleType),
                'started_at' => $startedAt,
                'ends_at' => $endsAt,
            ]);

            $created++;
        }

        return $created;
    }

    private function generateSubsystems(string $cycleType): array
    {
        return match ($cycleType) {
            'GROWTH_CYCLE' => [
                'irrigation' => ['status' => 'active', 'last_run' => now()->subHours(2)->toIso8601String()],
                'lighting' => ['status' => 'active', 'schedule' => '16/8'],
                'climate' => ['status' => 'active', 'temp_target' => 22, 'humidity_target' => 65],
            ],
            'MAINTENANCE_CYCLE' => [
                'cleaning' => ['status' => 'scheduled', 'next_run' => now()->addDays(7)->toIso8601String()],
                'calibration' => ['status' => 'pending', 'sensors' => ['ph', 'ec']],
            ],
            'CLEANING_CYCLE' => [
                'reservoir' => ['status' => 'completed', 'completed_at' => now()->subDays(1)->toIso8601String()],
                'pipes' => ['status' => 'scheduled', 'next_run' => now()->addDays(3)->toIso8601String()],
            ],
            default => [],
        };
    }
}

