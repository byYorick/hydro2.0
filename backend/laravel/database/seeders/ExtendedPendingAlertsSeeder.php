<?php

namespace Database\Seeders;

use App\Models\Zone;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;

/**
 * Сидер для ожидающих алертов
 */
class ExtendedPendingAlertsSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание ожидающих алертов ===');

        $zones = Zone::all();
        if ($zones->isEmpty()) {
            $this->command->warn('Зоны не найдены.');
            return;
        }

        $created = 0;

        foreach ($zones as $zone) {
            // Создаем несколько ожидающих алертов для активных зон
            if ($zone->status === 'RUNNING') {
                $created += $this->seedPendingAlertsForZone($zone);
            }
        }

        $this->command->info("Создано ожидающих алертов: {$created}");
        $this->command->info("Всего ожидающих алертов: " . DB::table('pending_alerts')->count());
    }

    private function seedPendingAlertsForZone(Zone $zone): int
    {
        $created = 0;
        $alertCount = rand(0, 3);

        $alertTypes = [
            ['type' => 'pH_HIGH', 'source' => 'biz', 'code' => 'PH_HIGH'],
            ['type' => 'EC_LOW', 'source' => 'biz', 'code' => 'EC_LOW'],
            ['type' => 'NODE_OFFLINE', 'source' => 'infra', 'code' => 'NODE_OFFLINE'],
            ['type' => 'WATER_LEVEL_LOW', 'source' => 'infra', 'code' => 'WATER_LOW'],
        ];

        $statuses = ['pending', 'failed', 'dlq'];
        $statusWeights = [70, 20, 10];

        for ($i = 0; $i < $alertCount; $i++) {
            $alertType = $alertTypes[rand(0, count($alertTypes) - 1)];
            
            // Выбираем статус по весам
            $rand = rand(1, 100);
            $cumulative = 0;
            $status = 'pending';
            foreach ($statuses as $index => $stat) {
                $cumulative += $statusWeights[$index];
                if ($rand <= $cumulative) {
                    $status = $stat;
                    break;
                }
            }

            $attempts = match ($status) {
                'pending' => rand(0, 2),
                'failed' => rand(3, 5),
                'dlq' => 3,
                default => 0,
            };

            DB::table('pending_alerts')->insert([
                'zone_id' => $zone->id,
                'source' => $alertType['source'],
                'code' => $alertType['code'],
                'type' => $alertType['type'],
                'details' => json_encode([
                    'message' => "Ожидающий алерт: {$alertType['type']} для зоны {$zone->name}",
                    'severity' => 'warning',
                ]),
                'attempts' => $attempts,
                'max_attempts' => 3,
                'next_retry_at' => $status === 'pending' ? now()->addMinutes(rand(1, 30)) : null,
                'moved_to_dlq_at' => $status === 'dlq' ? now()->subMinutes(rand(1, 120)) : null,
                'status' => $status,
                'last_error' => $status === 'failed' ? 'Ошибка отправки алерта' : null,
                'created_at' => now()->subHours(rand(0, 24)),
                'updated_at' => now()->subHours(rand(0, 24)),
            ]);

            $created++;
        }

        return $created;
    }
}
