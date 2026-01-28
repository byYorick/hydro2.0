<?php

namespace App\Console\Commands;

use App\Models\NodeChannel;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

class CleanupNodeChannelsGpio extends Command
{
    protected $signature = 'nodes:cleanup-gpio {--dry-run : Только показать, что будет изменено}';

    protected $description = 'Удалить gpio/pin из node_channels.config (аппаратные поля хранятся только в прошивке)';

    public function handle(): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $updated = 0;

        NodeChannel::chunkById(200, function ($channels) use (&$updated, $dryRun) {
            foreach ($channels as $channel) {
                $config = $channel->config ?? [];
                $cleaned = $this->stripForbidden($config);

                if ($cleaned === $config) {
                    continue;
                }

                $updated++;
                $this->line(sprintf(
                    '%s channel=%s removed gpio/pin',
                    $dryRun ? '[DRY RUN]' : '[UPDATE]',
                    $channel->channel
                ));

                if (! $dryRun) {
                    $channel->config = $cleaned;
                    $channel->save();
                }
            }
        });

        $this->info("Processed {$updated} channel configs");
        return Command::SUCCESS;
    }

    private function stripForbidden(array $config): array
    {
        unset($config['gpio'], $config['pin']);

        foreach ($config as $key => $value) {
            if (is_array($value)) {
                $config[$key] = $this->stripForbidden($value);
            }
        }

        return $config;
    }
}
