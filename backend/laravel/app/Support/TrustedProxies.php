<?php

namespace App\Support;

/**
 * Список доверенных reverse-proxy для TrustProxies.
 *
 * Пустое значение и отсутствие переменной не означают «доверять всем».
 * Явный `*` остаётся аварийным переключателем и в проде не используется.
 */
final class TrustedProxies
{
    /**
     * RFC1918: покрывает типовые сети Docker bridge (172.16.0.0/12) и LAN.
     *
     * @var list<string>
     */
    public const DEFAULT = [
        '10.0.0.0/8',
        '172.16.0.0/12',
        '192.168.0.0/16',
    ];

    /**
     * @return list<string>|'*'
     */
    public static function resolve(?string $raw): array|string
    {
        if ($raw === null) {
            return self::DEFAULT;
        }

        $trimmed = trim($raw);
        if ($trimmed === '') {
            return [];
        }

        if ($trimmed === '*') {
            return '*';
        }

        $proxies = array_values(array_filter(
            array_map(static fn (string $item): string => trim($item), explode(',', $trimmed)),
            static fn (string $item): bool => $item !== '',
        ));

        return $proxies;
    }
}
