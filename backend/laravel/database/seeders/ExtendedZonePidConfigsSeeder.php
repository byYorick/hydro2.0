<?php

namespace Database\Seeders;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZonePidConfig;
use Illuminate\Database\Seeder;

/**
 * Сидер для PID конфигураций зон
 */
class ExtendedZonePidConfigsSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание PID конфигураций зон ===');

        $zones = Zone::all();
        if ($zones->isEmpty()) {
            $this->command->warn('Зоны не найдены.');
            return;
        }

        $users = User::all();
        $adminUser = $users->firstWhere('role', 'admin') ?? $users->first();

        $created = 0;

        foreach ($zones as $zone) {
            // Создаем PID конфигурации для pH и EC
            $created += $this->seedPidConfigForZone($zone, 'ph', $adminUser);
            $created += $this->seedPidConfigForZone($zone, 'ec', $adminUser);
        }

        $this->command->info("Создано PID конфигураций: {$created}");
        $this->command->info("Всего PID конфигураций: " . ZonePidConfig::count());
    }

    private function seedPidConfigForZone(Zone $zone, string $type, ?User $user): int
    {
        $exists = ZonePidConfig::where('zone_id', $zone->id)
            ->where('type', $type)
            ->exists();

        if ($exists) {
            return 0;
        }

        $config = match ($type) {
            'ph' => [
                'target' => rand(58, 65) / 10, // 5.8 - 6.5
                'dead_zone' => 0.1,
                'close_zone' => 0.2,
                'far_zone' => 0.5,
                'zone_coeffs' => [
                    'close' => [
                        'kp' => rand(10, 20) / 10,
                        'ki' => rand(5, 15) / 10,
                        'kd' => rand(1, 5) / 10,
                    ],
                    'far' => [
                        'kp' => rand(20, 40) / 10,
                        'ki' => rand(10, 25) / 10,
                        'kd' => rand(5, 10) / 10,
                    ],
                ],
                'max_output' => 100,
                'min_interval_ms' => 5000,
                'enable_autotune' => true,
                'adaptation_rate' => 0.1,
            ],
            'ec' => [
                'target' => rand(15, 25) / 10, // 1.5 - 2.5
                'dead_zone' => 0.1,
                'close_zone' => 0.2,
                'far_zone' => 0.5,
                'zone_coeffs' => [
                    'close' => [
                        'kp' => rand(10, 20) / 10,
                        'ki' => rand(5, 15) / 10,
                        'kd' => rand(1, 5) / 10,
                    ],
                    'far' => [
                        'kp' => rand(20, 40) / 10,
                        'ki' => rand(10, 25) / 10,
                        'kd' => rand(5, 10) / 10,
                    ],
                ],
                'max_output' => 100,
                'min_interval_ms' => 10000,
                'enable_autotune' => true,
                'adaptation_rate' => 0.1,
            ],
            default => [],
        };

        ZonePidConfig::create([
            'zone_id' => $zone->id,
            'type' => $type,
            'config' => $config,
            'updated_by' => $user?->id,
            'updated_at' => now()->subDays(rand(1, 30)),
        ]);

        return 1;
    }
}

