<?php

namespace App\Console\Commands;

use Illuminate\Console\Command as ConsoleCommand;
use Illuminate\Support\Facades\DB;
use Carbon\Carbon;
use App\Models\Command;
use App\Models\CommandsArchive;

class ArchiveOldCommands extends ConsoleCommand
{
    protected $signature = 'commands:archive 
                            {--days=90 : Количество дней для хранения команд перед архивированием}';

    protected $description = 'Архивирует старые команды из commands в commands_archive (согласно DATA_RETENTION_POLICY.md: 90 дней hot)';

    public function handle()
    {
        $days = (int) $this->option('days');
        $cutoffDate = Carbon::now()->subDays($days);

        $this->info("Архивирование команд старше {$days} дней (до {$cutoffDate->toDateTimeString()})...");

        // Получаем команды для архивирования
        // Не архивируем команды в статусе QUEUED (ожидающие отправки)
        $commands = Command::where('created_at', '<', $cutoffDate)
            ->where('status', '!=', Command::STATUS_QUEUED)
            ->get();

        $archivedCount = 0;

        foreach ($commands as $command) {
            try {
                // Проверяем, не заархивирована ли уже команда
                $exists = CommandsArchive::where('cmd_id', $command->cmd_id)->exists();
                if ($exists) {
                    // Если уже заархивирована, просто удаляем из основной таблицы
                    $command->delete();
                    $archivedCount++;
                    continue;
                }

                // Создаем запись в архиве
                CommandsArchive::create([
                    'zone_id' => $command->zone_id,
                    'node_id' => $command->node_id,
                    'channel' => $command->channel,
                    'cmd' => $command->cmd,
                    'params' => $command->params,
                    'status' => $command->status,
                    'cmd_id' => $command->cmd_id,
                    'created_at' => $command->created_at,
                    'sent_at' => $command->sent_at,
                    'ack_at' => $command->ack_at,
                    'failed_at' => $command->failed_at,
                    'archived_at' => Carbon::now(),
                ]);

                // Удаляем из основной таблицы
                $command->delete();
                $archivedCount++;
            } catch (\Exception $e) {
                $this->warn("Ошибка при архивировании команды {$command->cmd_id}: {$e->getMessage()}");
            }
        }

        $this->info("Заархивировано команд: {$archivedCount}");
        return ConsoleCommand::SUCCESS;
    }
}

