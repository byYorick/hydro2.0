<?php

declare(strict_types=1);

namespace App\Support\Hydroponics;

use App\Enums\HydroSystem;
use RuntimeException;

/**
 * Канон hydro_system (ADR-0001). Файл schemas/hydro_system.enum.json — снимок для PHP и AE3.
 * Пустой тип не отказ: зона без явного типа остаётся каплей.
 */
final class HydroponicSystemCatalog
{
    /**
     * @var array<string, mixed>|null
     */
    private static ?array $catalog = null;

    /**
     * @return list<string>
     */
    public static function canonicalTypes(): array
    {
        return self::stringList('canonical');
    }

    /**
     * Типы, для которых AE3 уже имеет гидравлический граф.
     *
     * @return list<string>
     */
    public static function implementedTypes(): array
    {
        return self::stringList('implemented');
    }

    /**
     * @return list<string>
     */
    public static function supportedTypes(): array
    {
        return self::implementedTypes();
    }

    /**
     * @return list<string>
     */
    public static function needsReviewTypes(): array
    {
        return self::stringList('needs_review');
    }

    /**
     * @return array<string, string>
     */
    public static function aliases(): array
    {
        $aliases = self::catalog()['aliases'] ?? [];
        if (! is_array($aliases)) {
            return [];
        }

        $normalized = [];
        foreach ($aliases as $from => $to) {
            if (is_string($from) && is_string($to) && trim($from) !== '' && trim($to) !== '') {
                $normalized[strtolower(trim($from))] = strtolower(trim($to));
            }
        }

        return $normalized;
    }

    /**
     * @return array{canonical: list<string>, implemented: list<string>, needs_review: list<string>, aliases: array<string, string>}
     */
    public static function publicPayload(): array
    {
        return [
            'canonical' => self::canonicalTypes(),
            'implemented' => self::implementedTypes(),
            'supported' => self::implementedTypes(),
            'needs_review' => self::needsReviewTypes(),
            'aliases' => self::aliases(),
        ];
    }

    public static function canonicalize(?string $raw): ?string
    {
        if ($raw === null) {
            return null;
        }

        $token = strtolower(trim($raw));
        if ($token === '') {
            return null;
        }

        $token = str_replace(' ', '_', $token);

        return self::aliases()[$token] ?? $token;
    }

    public static function isImplemented(?string $raw): bool
    {
        $canonical = self::canonicalize($raw);

        return $canonical !== null && in_array($canonical, self::implementedTypes(), true);
    }

    /**
     * Код отказа ADR-0001 или null, если тип можно исполнять.
     */
    public static function refusalCode(?string $raw, ?string $environment = null): ?string
    {
        $canonical = self::canonicalize($raw);
        if ($canonical === null) {
            return null;
        }

        if (in_array($canonical, self::needsReviewTypes(), true)) {
            return 'hydro_system_needs_review';
        }

        $known = in_array($canonical, self::canonicalTypes(), true);
        if (! $known) {
            return 'hydro_system_unknown';
        }

        if (self::environmentForbids($canonical, $environment)) {
            return 'hydro_system_environment_forbidden';
        }

        if (! in_array($canonical, self::implementedTypes(), true)) {
            return 'hydro_system_not_implemented';
        }

        return null;
    }

    public static function rejectionMessage(string $code, string $requestedType, ?string $environment = null): string
    {
        $messages = self::catalog()['messages'] ?? [];
        $template = is_array($messages) && is_string($messages[$code] ?? null)
            ? $messages[$code]
            : 'Тип гидропонной системы «{requested}» нельзя запустить.';

        return strtr($template, [
            '{requested}' => $requestedType,
            '{supported}' => implode(', ', self::implementedTypes()),
            '{canonical}' => implode(', ', self::canonicalTypes()),
            '{environment}' => $environment ?? '',
        ]);
    }

    public static function assertEnumMatchesSnapshot(): void
    {
        $enumValues = array_map(static fn (HydroSystem $case): string => $case->value, HydroSystem::cases());
        sort($enumValues);
        $canonical = self::canonicalTypes();
        $sorted = $canonical;
        sort($sorted);
        if ($enumValues !== $sorted) {
            throw new RuntimeException('HydroSystem enum разошёлся со schemas/hydro_system.enum.json');
        }
    }

    public static function flushCache(): void
    {
        self::$catalog = null;
    }

    public static function environmentForbids(string $canonical, ?string $environment): bool
    {
        if ($environment === null || strtolower(trim($environment)) !== 'outdoor') {
            return false;
        }

        $only = self::catalog()['environment']['outdoor_only'] ?? ['drip'];
        if (! is_array($only)) {
            $only = ['drip'];
        }

        return ! in_array($canonical, $only, true);
    }

    /**
     * @return list<string>
     */
    private static function stringList(string $key): array
    {
        $values = self::catalog()[$key] ?? [];
        if (! is_array($values)) {
            return [];
        }

        return array_values(array_map(
            static fn (string $value): string => strtolower(trim($value)),
            array_filter($values, static fn ($value): bool => is_string($value) && trim($value) !== ''),
        ));
    }

    /**
     * @return array<string, mixed>
     */
    private static function catalog(): array
    {
        if (self::$catalog !== null) {
            return self::$catalog;
        }

        $path = self::catalogPath();
        $decoded = json_decode((string) file_get_contents($path), true);
        if (! is_array($decoded)) {
            throw new RuntimeException("Каталог hydro_system не JSON: {$path}");
        }

        self::$catalog = $decoded;

        return self::$catalog;
    }

    private static function catalogPath(): string
    {
        $override = getenv('HYDRO_SYSTEM_ENUM_PATH');
        $candidates = array_filter([
            is_string($override) && $override !== '' ? $override : null,
            '/schemas/hydro_system.enum.json',
            dirname(base_path(), 2).'/schemas/hydro_system.enum.json',
            dirname(base_path()).'/../schemas/hydro_system.enum.json',
        ]);

        foreach ($candidates as $candidate) {
            if (is_string($candidate) && is_file($candidate)) {
                return $candidate;
            }
        }

        throw new RuntimeException('Не найден schemas/hydro_system.enum.json');
    }
}
