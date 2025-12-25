<?php

namespace Database\Seeders;

use App\Models\Command;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Models\UnassignedNodeError;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;

/**
 * Сидер для архивных таблиц (команды, события, ошибки)
 */
class ExtendedArchivesSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание архивных данных ===');

        $commandsArchived = $this->seedCommandsArchive();
        $eventsArchived = $this->seedZoneEventsArchive();
        $errorsArchived = $this->seedUnassignedNodeErrorsArchive();

        $this->command->info("Архивировано команд: {$commandsArchived}");
        $this->command->info("Архивировано событий: {$eventsArchived}");
        $this->command->info("Архивировано ошибок: {$errorsArchived}");
    }

    private function seedCommandsArchive(): int
    {
        $archived = 0;

        // Берем старые завершенные команды для архивации
        $oldCommands = Command::whereIn('status', ['DONE', 'FAILED', 'TIMEOUT'])
            ->where('created_at', '<', now()->subDays(30))
            ->limit(100)
            ->get();

        foreach ($oldCommands as $command) {
            $exists = DB::table('commands_archive')
                ->where('cmd_id', $command->cmd_id)
                ->exists();

            if ($exists) {
                continue;
            }

            DB::table('commands_archive')->insert([
                'zone_id' => $command->zone_id,
                'node_id' => $command->node_id,
                'channel' => $command->channel,
                'cmd' => $command->cmd,
                'params' => json_encode($command->params),
                'status' => strtolower($command->status),
                'cmd_id' => $command->cmd_id,
                'created_at' => $command->created_at,
                'sent_at' => $command->sent_at,
                'ack_at' => $command->ack_at,
                'failed_at' => $command->failed_at,
                'archived_at' => now()->subDays(rand(1, 7)),
            ]);

            $archived++;
        }

        return $archived;
    }

    private function seedZoneEventsArchive(): int
    {
        $archived = 0;

        // Берем старые события для архивации
        $oldEvents = ZoneEvent::where('created_at', '<', now()->subDays(30))
            ->limit(200)
            ->get();

        foreach ($oldEvents as $event) {
            $exists = DB::table('zone_events_archive')
                ->where('zone_id', $event->zone_id)
                ->where('type', $event->type)
                ->where('created_at', $event->created_at)
                ->exists();

            if ($exists) {
                continue;
            }

            DB::table('zone_events_archive')->insert([
                'zone_id' => $event->zone_id,
                'type' => $event->type,
                'details' => json_encode($event->details),
                'created_at' => $event->created_at,
                'archived_at' => now()->subDays(rand(1, 7)),
            ]);

            $archived++;
        }

        return $archived;
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

