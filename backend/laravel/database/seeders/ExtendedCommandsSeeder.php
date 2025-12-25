<?php

namespace Database\Seeders;

use App\Models\Command;
use App\Models\DeviceNode;
use App\Models\Zone;
use Illuminate\Database\Seeder;
use Illuminate\Support\Str;

/**
 * Расширенный сидер для команд
 * Создает разнообразные команды с разными статусами и типами
 */
class ExtendedCommandsSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание расширенных команд ===');

        $zones = Zone::all();
        if ($zones->isEmpty()) {
            $this->command->warn('Зоны не найдены.');
            return;
        }

        $commandsCreated = 0;

        foreach ($zones as $zone) {
            $nodes = DeviceNode::where('zone_id', $zone->id)->get();
            if ($nodes->isEmpty()) {
                continue;
            }

            $commandsCreated += $this->seedCommandsForZone($zone, $nodes);
        }

        $this->command->info("Создано команд: " . number_format($commandsCreated));
        $this->command->info("Всего команд: " . Command::count());
    }

    private function seedCommandsForZone(Zone $zone, $nodes): int
    {
        $commandsCreated = 0;
        
        // Количество дней истории зависит от статуса зоны
        $daysBack = match ($zone->status) {
            'RUNNING' => 30,
            'PAUSED' => 14,
            'STOPPED' => 7,
            default => 7,
        };

        $commandTypes = [
            'DOSE' => ['ph_up', 'ph_down', 'nutrient_a', 'nutrient_b'],
            'IRRIGATE' => ['start', 'stop', 'set_duration'],
            'SET_LIGHT' => ['on', 'off', 'set_intensity'],
            'SET_CLIMATE' => ['set_temperature', 'set_humidity', 'set_fan'],
            'READ_SENSOR' => ['ph', 'ec', 'temperature', 'humidity'],
            'CALIBRATE' => ['ph', 'ec'],
            'PUMP_CONTROL' => ['start', 'stop', 'set_speed'],
        ];

        $statuses = [
            Command::STATUS_QUEUED => 5,
            Command::STATUS_SENT => 10,
            Command::STATUS_ACCEPTED => 15,
            Command::STATUS_DONE => 60,
            Command::STATUS_FAILED => 5,
            Command::STATUS_TIMEOUT => 3,
            Command::STATUS_SEND_FAILED => 2,
        ];

        $now = now();
        $startDate = $now->copy()->subDays($daysBack)->startOfDay();

        // Генерируем команды для каждого дня
        $currentDate = $startDate->copy();
        while ($currentDate->lt($now)) {
            // Количество команд в день зависит от статуса зоны
            $commandsPerDay = match ($zone->status) {
                'RUNNING' => rand(10, 30),
                'PAUSED' => rand(3, 10),
                'STOPPED' => rand(1, 5),
                default => 5,
            };

            for ($i = 0; $i < $commandsPerDay; $i++) {
                $node = $nodes->random();
                $cmdType = array_rand($commandTypes);
                $cmdSubType = $commandTypes[$cmdType][array_rand($commandTypes[$cmdType])];
                
                // Выбираем статус по весам
                $status = $this->selectWeightedStatus($statuses);
                
                // Генерируем временные метки
                $createdAt = $currentDate->copy()->addHours(rand(0, 23))->addMinutes(rand(0, 59));
                $sentAt = in_array($status, [Command::STATUS_SENT, Command::STATUS_ACCEPTED, Command::STATUS_DONE, Command::STATUS_FAILED, Command::STATUS_TIMEOUT])
                    ? $createdAt->copy()->addSeconds(rand(1, 30))
                    : null;
                
                $ackAt = in_array($status, [Command::STATUS_ACCEPTED, Command::STATUS_DONE, Command::STATUS_FAILED, Command::STATUS_TIMEOUT])
                    ? ($sentAt ? $sentAt->copy()->addSeconds(rand(1, 60)) : $createdAt->copy()->addSeconds(rand(1, 60)))
                    : null;
                
                $failedAt = in_array($status, [Command::STATUS_FAILED, Command::STATUS_TIMEOUT, Command::STATUS_SEND_FAILED])
                    ? ($ackAt ? $ackAt->copy()->addSeconds(rand(1, 300)) : ($sentAt ? $sentAt->copy()->addSeconds(rand(1, 300)) : $createdAt->copy()->addSeconds(rand(1, 300))))
                    : null;

                $params = $this->generateCommandParams($cmdType, $cmdSubType);
                
                $errorCode = in_array($status, [Command::STATUS_FAILED, Command::STATUS_TIMEOUT, Command::STATUS_SEND_FAILED])
                    ? rand(1000, 9999)
                    : null;
                
                $errorMessage = $errorCode
                    ? "Ошибка выполнения команды: {$cmdType}"
                    : null;

                $resultCode = $status === Command::STATUS_DONE ? 0 : null;
                $durationMs = $ackAt && $sentAt ? $sentAt->diffInMilliseconds($ackAt) : null;

                Command::create([
                    'zone_id' => $zone->id,
                    'node_id' => $node->id,
                    'channel' => $this->getChannelForCommand($cmdType, $cmdSubType),
                    'cmd' => $cmdType,
                    'params' => $params,
                    'status' => $status,
                    'cmd_id' => Str::uuid()->toString(),
                    'sent_at' => $sentAt,
                    'ack_at' => $ackAt,
                    'failed_at' => $failedAt,
                    'error_code' => $errorCode,
                    'error_message' => $errorMessage,
                    'result_code' => $resultCode,
                    'duration_ms' => $durationMs,
                    'created_at' => $createdAt,
                ]);

                $commandsCreated++;
            }

            $currentDate->addDay();
        }

        return $commandsCreated;
    }

    private function selectWeightedStatus(array $statuses): string
    {
        $totalWeight = array_sum($statuses);
        $random = rand(1, $totalWeight);
        $cumulative = 0;

        foreach ($statuses as $status => $weight) {
            $cumulative += $weight;
            if ($random <= $cumulative) {
                return $status;
            }
        }

        return Command::STATUS_QUEUED;
    }

    private function generateCommandParams(string $cmdType, string $cmdSubType): array
    {
        return match ($cmdType) {
            'DOSE' => [
                'action' => $cmdSubType,
                'amount' => rand(10, 100) / 10,
                'unit' => 'ml',
            ],
            'IRRIGATE' => [
                'action' => $cmdSubType,
                'duration' => $cmdSubType === 'set_duration' ? rand(5, 30) : null,
            ],
            'SET_LIGHT' => [
                'action' => $cmdSubType,
                'intensity' => $cmdSubType === 'set_intensity' ? rand(20, 100) : null,
            ],
            'SET_CLIMATE' => [
                'action' => $cmdSubType,
                'value' => match ($cmdSubType) {
                    'set_temperature' => rand(18, 26),
                    'set_humidity' => rand(50, 70),
                    'set_fan' => rand(30, 100),
                    default => null,
                },
            ],
            'READ_SENSOR' => [
                'sensor' => $cmdSubType,
            ],
            'CALIBRATE' => [
                'sensor' => $cmdSubType,
                'point' => rand(1, 3),
            ],
            'PUMP_CONTROL' => [
                'action' => $cmdSubType,
                'speed' => $cmdSubType === 'set_speed' ? rand(30, 100) : null,
            ],
            default => ['action' => $cmdSubType],
        };
    }

    private function getChannelForCommand(string $cmdType, string $cmdSubType): ?string
    {
        return match ($cmdType) {
            'DOSE' => in_array($cmdSubType, ['ph_up', 'ph_down']) ? 'ph' : 'ec',
            'IRRIGATE' => 'pump1',
            'SET_LIGHT' => 'light',
            'SET_CLIMATE' => match ($cmdSubType) {
                'set_temperature', 'set_humidity' => 'climate',
                'set_fan' => 'fan',
                default => null,
            },
            'READ_SENSOR' => $cmdSubType,
            'CALIBRATE' => $cmdSubType,
            'PUMP_CONTROL' => 'pump1',
            default => null,
        };
    }
}

