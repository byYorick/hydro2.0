<?php

namespace Database\Seeders;

use App\Models\Command;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Models\UnassignedNodeError;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;

/**
 * Сидер для архивных таблиц (только ошибки узлов)
 * 
 * DEPRECATED: commands_archive и zone_events_archive удалены.
 * Используется партиционирование и retention policies вместо архивных таблиц.
 */
class ExtendedArchivesSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание архивных данных ===');

        $errorsArchived = $this->seedUnassignedNodeErrorsArchive();

        $this->command->info("Архивировано ошибок: {$errorsArchived}");
    }

    /**
     * @deprecated Архивные таблицы commands_archive и zone_events_archive удалены.
     * Используется партиционирование и retention policies вместо архивных таблиц.
     */
    private function seedCommandsArchive(): int
    {
        // Архивные таблицы удалены - используем партиционирование
        return 0;
    }

    /**
     * @deprecated Архивная таблица zone_events_archive удалена. Используется партиционирование.
     */
    private function seedZoneEventsArchive(): int
    {
        return 0;
    }

    private function seedUnassignedNodeErrorsArchive(): int
    {
        $archived = 0;

        // Берем старые ошибки, которые были привязаны к узлам
        $oldErrors = UnassignedNodeError::whereNotNull('node_id')
            ->where('last_seen_at', '<', now()->subDays(7))
            ->limit(50)
            ->get();

        foreach ($oldErrors as $error) {
            $exists = DB::table('unassigned_node_errors_archive')
                ->where('hardware_id', $error->hardware_id)
                ->where('topic', $error->topic)
                ->where('first_seen_at', $error->first_seen_at)
                ->exists();

            if ($exists) {
                continue;
            }

            // Получаем зону узла
            $node = \App\Models\DeviceNode::find($error->node_id);
            $zoneId = $node?->zone_id;

            DB::table('unassigned_node_errors_archive')->insert([
                'hardware_id' => $error->hardware_id,
                'error_message' => $error->error_message,
                'error_code' => $error->error_code,
                'severity' => $error->severity ?? 'ERROR',
                'topic' => $error->topic,
                'last_payload' => json_encode($error->last_payload),
                'count' => $error->count,
                'first_seen_at' => $error->first_seen_at,
                'last_seen_at' => $error->last_seen_at,
                'node_id' => $error->node_id,
                'archived_at' => now()->subDays(rand(1, 7)),
                'attached_at' => $error->node_id ? now()->subDays(rand(1, 14)) : null,
                'attached_zone_id' => $zoneId,
            ]);

            $archived++;
        }

        return $archived;
    }
}

