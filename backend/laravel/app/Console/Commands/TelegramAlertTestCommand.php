<?php

namespace App\Console\Commands;

use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\TelegramAlertNotifier;
use Illuminate\Console\Command;

class TelegramAlertTestCommand extends Command
{
    protected $signature = 'alerts:telegram-test
                            {--text=hydro2.0 telegram test : Текст тестового сообщения}';

    protected $description = 'Проверить доставку алертов в Telegram (этап E)';

    public function handle(
        TelegramAlertNotifier $notifier,
        AutomationConfigDocumentService $documents,
    ): int {
        if (! $notifier->isConfigured()) {
            $this->error('Telegram не настроен: задайте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_IDS в backend/.env');
            $this->rememberTelegramTest(documents: $documents, ok: false);

            return self::FAILURE;
        }

        if (! config('alerts.telegram.enabled', true)) {
            $this->error('ALERTS_TELEGRAM_ENABLED=false');
            $this->rememberTelegramTest(documents: $documents, ok: false);

            return self::FAILURE;
        }

        $text = (string) $this->option('text');
        $sent = $notifier->sendTestMessage($text);
        if (! $sent) {
            $this->error('Bot API не принял сообщение. Проверьте токен и chat_id.');
            $this->rememberTelegramTest(documents: $documents, ok: false);

            return self::FAILURE;
        }

        $this->rememberTelegramTest(documents: $documents, ok: true);
        $this->info('Тестовое сообщение отправлено в Telegram.');

        return self::SUCCESS;
    }

    private function rememberTelegramTest(
        AutomationConfigDocumentService $documents,
        bool $ok,
    ): void {
        $payload = $documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_ALERT_POLICIES,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            true,
        );
        $payload['telegram_test_ok'] = $ok;
        $payload['telegram_test_at'] = now()->toIso8601String();
        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_ALERT_POLICIES,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            $payload,
            null,
            'alerts:telegram-test',
        );
    }
}
