<?php

namespace App\Console\Commands;

use Illuminate\Console\Command as ConsoleCommand;
use Carbon\Carbon;
use App\Models\ZoneEvent;
use App\Models\ZoneEventsArchive;

class ArchiveOldZoneEvents extends ConsoleCommand
{
    protected $signature = 'zone-events:archive 
                            {--days=180 : Количество дней для хранения событий перед архивированием}';

    protected $description = 'Архивирует старые события из zone_events в zone_events_archive (согласно DATA_RETENTION_POLICY.md: 180 дней hot)';

    public function handle()
    {
        $days = (int) $this->option('days');
        $cutoffDate = Carbon::now()->subDays($days);

        $this->info("Архивирование событий старше {$days} дней (до {$cutoffDate->toDateTimeString()})...");

        // Получаем события для архивирования
        $events = ZoneEvent::where('created_at', '<', $cutoffDate)->get();

        $archivedCount = 0;

        foreach ($events as $event) {
            try {
                // Создаем запись в архиве
                ZoneEventsArchive::create([
                    'zone_id' => $event->zone_id,
                    'type' => $event->type,
                    'details' => $event->details,
                    'created_at' => $event->created_at,
                    'archived_at' => Carbon::now(),
                ]);

                // Удаляем из основной таблицы
                $event->delete();
                $archivedCount++;
            } catch (\Exception $e) {
                $this->warn("Ошибка при архивировании события {$event->id}: {$e->getMessage()}");
            }
        }

        $this->info("Заархивировано событий: {$archivedCount}");
        return ConsoleCommand::SUCCESS;
    }
}

