<?php

namespace App\Console\Commands;

use App\Services\TelegramAlertNotifier;
use Illuminate\Console\Command;

class TelegramAlertTestCommand extends Command
{
    protected $signature = 'alerts:telegram-test
                            {--text=hydro2.0 telegram test : Текст тестового сообщения}';

    protected $description = 'Проверить доставку алертов в Telegram (этап E)';

    public function handle(TelegramAlertNotifier $notifier): int
    {
        if (! $notifier->isConfigured()) {
            $this->error('Telegram не настроен: задайте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_IDS в backend/.env');

            return self::FAILURE;
        }

        if (! config('alerts.telegram.enabled', true)) {
            $this->error('ALERTS_TELEGRAM_ENABLED=false');

            return self::FAILURE;
        }

        $text = (string) $this->option('text');
        $sent = $notifier->sendTestMessage($text);
        if (! $sent) {
            $this->error('Bot API не принял сообщение. Проверьте токен и chat_id.');

            return self::FAILURE;
        }

        $this->info('Тестовое сообщение отправлено в Telegram.');

        return self::SUCCESS;
    }
}
