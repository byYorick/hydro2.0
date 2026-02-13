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
        $alertCount = rand(1, 3);

        $alertTypes = [
            ['type' => 'pH_HIGH', 'source' => 'biz', 'code' => 'PH_HIGH'],
            ['type' => 'EC_LOW', 'source' => 'biz', 'code' => 'EC_LOW'],
            ['type' => 'NODE_OFFLINE', 'source' => 'infra', 'code' => 'NODE_OFFLINE'],
            ['type' => 'WATER_LEVEL_LOW', 'source' => 'infra', 'code' => 'WATER_LOW'],
        ];

        $alertStatuses = ['ACTIVE', 'RESOLVED'];
        $statusWeights = [80, 20];

        for ($i = 0; $i < $alertCount; $i++) {
            $alertType = $alertTypes[rand(0, count($alertTypes) - 1)];
            
            // Выбираем статус по весам
            $rand = rand(1, 100);
            $cumulative = 0;
            $status = 'ACTIVE';
            foreach ($alertStatuses as $index => $stat) {
                $cumulative += $statusWeights[$index];
                if ($rand <= $cumulative) {
                    $status = $stat;
                    break;
                }
            }

            $attempts = $status === 'ACTIVE' ? rand(0, 4) : rand(0, 1);
            $nextRetryAt = $status === 'ACTIVE'
                ? now()->addMinutes(rand(1, 30))
                : null;
            $lastError = $attempts > 0
                ? 'Ошибка отправки алерта в Laravel API'
                : null;

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
                'max_attempts' => 10,
                'next_retry_at' => $nextRetryAt,
                'moved_to_dlq_at' => null,
                'status' => $status,
                'last_error' => $lastError,
                'created_at' => now()->subHours(rand(0, 24)),
                'updated_at' => now()->subHours(rand(0, 24)),
            ]);

            $created++;
        }

        return $created;
    }
}
