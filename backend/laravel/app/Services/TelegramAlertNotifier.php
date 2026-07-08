<?php

declare(strict_types=1);

namespace App\Services;

use App\Models\Alert;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class TelegramAlertNotifier
{
    public function __construct(
        private AlertLocalizationService $alertLocalization,
    ) {}

    public function notifyIfEligible(Alert $alert): void
    {
        if (! $this->isConfigured()) {
            return;
        }

        if (! config('alerts.telegram.enabled', true)) {
            return;
        }

        if (! $this->isEligibleSeverity($alert)) {
            return;
        }

        $code = is_string($alert->code) ? trim($alert->code) : '';
        if ($code === '') {
            return;
        }

        if ($this->isDeduped($code, $alert->zone_id)) {
            Log::debug('Telegram alert notification deduplicated', [
                'alert_id' => $alert->id,
                'code' => $code,
                'zone_id' => $alert->zone_id,
            ]);

            return;
        }

        $this->send($alert);
    }

    public function isConfigured(): bool
    {
        $token = config('services.telegram.bot_token');
        $chatIds = config('services.telegram.chat_ids', []);

        return is_string($token) && $token !== '' && is_array($chatIds) && $chatIds !== [];
    }

    public function isEligibleSeverity(Alert $alert): bool
    {
        $severity = strtolower(trim((string) ($alert->severity ?? '')));
        $allowed = config('alerts.telegram.severities', ['critical', 'error']);

        return in_array($severity, $allowed, true);
    }

    public function isDeduped(string $code, ?int $zoneId): bool
    {
        $ttl = (int) config('alerts.telegram.dedup_ttl_seconds', 60);
        if ($ttl <= 0) {
            return false;
        }

        $key = $this->dedupCacheKey($code, $zoneId);

        return ! Cache::add($key, 1, $ttl);
    }

    public function dedupCacheKey(string $code, ?int $zoneId): string
    {
        $zoneSegment = $zoneId === null ? 'global' : (string) $zoneId;

        return sprintf('telegram_alert:%s:%s', $code, $zoneSegment);
    }

    private function send(Alert $alert): void
    {
        $token = (string) config('services.telegram.bot_token');
        $chatIds = config('services.telegram.chat_ids', []);
        $message = $this->buildMessage($alert);
        $url = sprintf('https://api.telegram.org/bot%s/sendMessage', $token);

        foreach ($chatIds as $chatId) {
            if (! is_string($chatId) || trim($chatId) === '') {
                continue;
            }

            try {
                $response = Http::timeout(5)
                    ->acceptJson()
                    ->post($url, [
                        'chat_id' => trim($chatId),
                        'text' => $message,
                        'parse_mode' => 'HTML',
                        'disable_web_page_preview' => true,
                    ]);

                if (! $response->successful()) {
                    Log::warning('Telegram alert notification failed', [
                        'alert_id' => $alert->id,
                        'chat_id' => $chatId,
                        'status' => $response->status(),
                        'body' => $response->body(),
                    ]);
                }
            } catch (\Throwable $e) {
                Log::error('Telegram alert notification exception', [
                    'alert_id' => $alert->id,
                    'chat_id' => $chatId,
                    'error' => $e->getMessage(),
                ]);
            }
        }
    }

    private function buildMessage(Alert $alert): string
    {
        $details = is_array($alert->details) ? $alert->details : [];
        $presentation = $this->alertLocalization->present(
            code: is_string($alert->code) ? $alert->code : null,
            type: is_string($alert->type) ? $alert->type : null,
            details: $details,
            source: is_string($alert->source) ? $alert->source : null,
        );

        $severity = strtoupper((string) ($alert->severity ?? 'unknown'));
        $zoneLabel = $alert->zone_id === null
            ? '—'
            : 'зона #'.(int) $alert->zone_id;

        $lines = [
            '<b>🚨 '.$this->escapeHtml($severity).'</b>',
            '<b>'.$this->escapeHtml($presentation['title']).'</b>',
            $this->escapeHtml($presentation['message']),
            '',
            'Код: <code>'.$this->escapeHtml((string) ($alert->code ?? 'unknown')).'</code>',
            'Зона: '.$this->escapeHtml($zoneLabel),
        ];

        $recommendation = trim((string) ($presentation['recommendation'] ?? ''));
        if ($recommendation !== '') {
            $lines[] = '';
            $lines[] = '<i>'.$this->escapeHtml($recommendation).'</i>';
        }

        return implode("\n", $lines);
    }

    private function escapeHtml(string $value): string
    {
        return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
    }
}
