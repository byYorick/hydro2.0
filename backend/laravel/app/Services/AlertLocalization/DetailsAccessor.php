<?php

declare(strict_types=1);

namespace App\Services\AlertLocalization;

/**
 * Безопасный доступ к $details-словарю алерта с нормализацией типов.
 */
class DetailsAccessor
{
    /**
     * @param array<string, mixed> $details
     * @param string[]             $keys
     */
    public function stringValue(array $details, array $keys): ?string
    {
        foreach ($keys as $key) {
            $value = $details[$key] ?? null;
            if (! is_string($value)) {
                continue;
            }

            $normalized = trim($value);
            if ($normalized !== '') {
                return $normalized;
            }
        }

        return null;
    }

    /**
     * @param array<string, mixed> $details
     * @param string[]             $keys
     */
    public function scalarValue(array $details, array $keys): ?string
    {
        foreach ($keys as $key) {
            if (! array_key_exists($key, $details)) {
                continue;
            }

            $value = $details[$key];
            if (! is_scalar($value)) {
                continue;
            }

            $normalized = trim((string) $value);
            if ($normalized !== '') {
                return $normalized;
            }
        }

        return null;
    }

    /**
     * @param array<string, mixed> $details
     * @param string[]             $keys
     */
    public function integerValue(array $details, array $keys): ?int
    {
        foreach ($keys as $key) {
            if (! array_key_exists($key, $details)) {
                continue;
            }

            $value = $details[$key];
            if (is_int($value)) {
                return $value;
            }

            if (is_string($value) && preg_match('/^-?\d+$/', trim($value)) === 1) {
                return (int) trim($value);
            }
        }

        return null;
    }

    public function looksLocalized(string $value): bool
    {
        return preg_match('/\p{Cyrillic}/u', $value) === 1;
    }
}
