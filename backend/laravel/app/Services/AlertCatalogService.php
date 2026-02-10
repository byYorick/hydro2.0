<?php

namespace App\Services;

use Illuminate\Support\Facades\Log;

class AlertCatalogService
{
    /**
     * @var array<int, array<string, mixed>>|null
     */
    private static ?array $cachedCodes = null;

    /**
     * @var array<string, array<string, mixed>>|null
     */
    private static ?array $cachedByCode = null;

    /**
     * @return array<int, array<string, mixed>>
     */
    public function all(): array
    {
        return $this->loadCatalog()['codes'];
    }

    /**
     * @return array<string, mixed>
     */
    public function metadata(): array
    {
        $catalog = $this->loadCatalog();

        return [
            'version' => $catalog['version'] ?? null,
            'updated_at' => $catalog['updated_at'] ?? null,
            'count' => count($catalog['codes']),
        ];
    }

    /**
     * @param array<string, mixed>|null $details
     * @return array<string, mixed>
     */
    public function resolve(?string $code, ?string $source = null, ?array $details = null): array
    {
        $normalizedCode = $this->normalizeCode($code);
        $byCode = $this->codesByCode();
        $entry = $normalizedCode !== '' ? ($byCode[$normalizedCode] ?? null) : null;

        $resolvedSource = $this->resolveSource($source, $normalizedCode, $entry, $details);
        $resolvedSeverity = $this->resolveSeverity($details, $entry, $normalizedCode);
        $resolvedCategory = $this->resolveCategory($details, $entry, $normalizedCode);
        $resolvedCode = $normalizedCode !== '' ? $normalizedCode : 'unknown_alert';

        return [
            'code' => $resolvedCode,
            'source' => $resolvedSource,
            'category' => $resolvedCategory,
            'severity' => $resolvedSeverity,
            'title' => $entry['title'] ?? $this->fallbackTitle($resolvedCode),
            'description' => $entry['description'] ?? 'Событие требует проверки по журналам сервиса.',
            'recommendation' => $entry['recommendation'] ?? 'Проверьте детали алерта и состояние сервисов.',
            'node_related' => $this->resolveNodeRelated($details, $entry, $resolvedCode),
        ];
    }

    public function normalizeCode(?string $code): string
    {
        $normalized = strtolower(trim((string) ($code ?? '')));

        if ($normalized === '') {
            return '';
        }

        return preg_replace('/[^a-z0-9_\-]/', '_', $normalized) ?? $normalized;
    }

    /**
     * @return array<string, mixed>
     */
    private function loadCatalog(): array
    {
        if (self::$cachedCodes !== null) {
            return [
                'codes' => self::$cachedCodes,
                'version' => config('app.alert_catalog_version'),
                'updated_at' => config('app.alert_catalog_updated_at'),
            ];
        }

        $candidatePaths = [
            base_path('alert_codes.json'),
            base_path('../alert_codes.json'),
            base_path('../../alert_codes.json'),
        ];

        $path = null;
        foreach ($candidatePaths as $candidatePath) {
            if (is_file($candidatePath)) {
                $path = $candidatePath;
                break;
            }
        }

        if (! is_string($path)) {
            Log::warning('Alert catalog file not found', ['paths' => $candidatePaths]);
            self::$cachedCodes = [];
            self::$cachedByCode = [];

            return [
                'codes' => [],
                'version' => null,
                'updated_at' => null,
            ];
        }

        $raw = file_get_contents($path);
        $decoded = is_string($raw) ? json_decode($raw, true) : null;

        if (! is_array($decoded)) {
            Log::warning('Alert catalog file has invalid JSON', ['path' => $path]);
            self::$cachedCodes = [];
            self::$cachedByCode = [];

            return [
                'codes' => [],
                'version' => null,
                'updated_at' => null,
            ];
        }

        $codes = isset($decoded['codes']) && is_array($decoded['codes']) ? $decoded['codes'] : [];
        $normalizedCodes = [];
        $byCode = [];

        foreach ($codes as $row) {
            if (! is_array($row)) {
                continue;
            }

            $normalizedCode = $this->normalizeCode($row['code'] ?? null);
            if ($normalizedCode === '') {
                continue;
            }

            $normalizedRow = [
                'code' => $normalizedCode,
                'source' => $this->normalizeSource($row['source'] ?? null),
                'category' => $this->normalizeCategory($row['category'] ?? null),
                'severity' => $this->normalizeSeverityValue($row['severity'] ?? null),
                'title' => trim((string) ($row['title'] ?? '')),
                'description' => trim((string) ($row['description'] ?? '')),
                'recommendation' => trim((string) ($row['recommendation'] ?? '')),
                'node_related' => (bool) ($row['node_related'] ?? false),
            ];

            $normalizedCodes[] = $normalizedRow;
            $byCode[$normalizedCode] = $normalizedRow;
        }

        self::$cachedCodes = $normalizedCodes;
        self::$cachedByCode = $byCode;

        return [
            'codes' => $normalizedCodes,
            'version' => $decoded['version'] ?? null,
            'updated_at' => $decoded['updated_at'] ?? null,
        ];
    }

    /**
     * @return array<string, array<string, mixed>>
     */
    private function codesByCode(): array
    {
        if (self::$cachedByCode !== null) {
            return self::$cachedByCode;
        }

        $this->loadCatalog();

        return self::$cachedByCode ?? [];
    }

    /**
     * @param array<string, mixed>|null $entry
     * @param array<string, mixed>|null $details
     */
    private function resolveSource(?string $source, string $code, ?array $entry, ?array $details): string
    {
        $sourceFromPayload = $this->normalizeSource($source);
        if ($sourceFromPayload !== null) {
            return $sourceFromPayload;
        }

        $sourceFromDetails = $this->normalizeSource($details['source'] ?? null);
        if ($sourceFromDetails !== null) {
            return $sourceFromDetails;
        }

        $sourceFromCatalog = $this->normalizeSource($entry['source'] ?? null);
        if ($sourceFromCatalog !== null) {
            return $sourceFromCatalog;
        }

        if (str_starts_with($code, 'node_error_') || $code === 'node_error') {
            return 'node';
        }

        if (str_starts_with($code, 'infra_')) {
            return 'infra';
        }

        if (str_starts_with($code, 'biz_')) {
            return 'biz';
        }

        return 'infra';
    }

    /**
     * @param array<string, mixed>|null $details
     * @param array<string, mixed>|null $entry
     */
    private function resolveSeverity(?array $details, ?array $entry, string $code): string
    {
        $fromDetails = $this->normalizeSeverityValue($details['severity'] ?? null)
            ?? $this->normalizeSeverityValue($details['level'] ?? null);

        if ($fromDetails !== null) {
            return $fromDetails;
        }

        $fromCatalog = $this->normalizeSeverityValue($entry['severity'] ?? null);
        if ($fromCatalog !== null) {
            return $fromCatalog;
        }

        if (
            str_contains($code, 'timeout')
            || str_contains($code, 'circuit_open')
            || str_contains($code, 'db_unreachable')
            || str_contains($code, 'mqtt_down')
        ) {
            return 'critical';
        }

        if (str_contains($code, 'failed') || str_contains($code, 'error')) {
            return 'error';
        }

        return 'warning';
    }

    /**
     * @param array<string, mixed>|null $details
     * @param array<string, mixed>|null $entry
     */
    private function resolveCategory(?array $details, ?array $entry, string $code): string
    {
        $fromDetails = $this->normalizeCategory($details['category'] ?? null);
        if ($fromDetails !== null) {
            return $fromDetails;
        }

        $fromCatalog = $this->normalizeCategory($entry['category'] ?? null);
        if ($fromCatalog !== null) {
            return $fromCatalog;
        }

        if (str_starts_with($code, 'node_error_') || $code === 'node_error') {
            return 'node';
        }

        if (str_starts_with($code, 'biz_')) {
            return 'agronomy';
        }

        if (str_contains($code, 'config')) {
            return 'config';
        }

        if (str_contains($code, 'pump') || str_contains($code, 'flow') || str_contains($code, 'dry_run')) {
            return 'safety';
        }

        if (str_starts_with($code, 'infra_')) {
            return 'infrastructure';
        }

        return 'other';
    }

    /**
     * @param array<string, mixed>|null $details
     * @param array<string, mixed>|null $entry
     */
    private function resolveNodeRelated(?array $details, ?array $entry, string $code): bool
    {
        if (is_array($entry) && isset($entry['node_related'])) {
            return (bool) $entry['node_related'];
        }

        if (
            isset($details['node_uid'])
            || isset($details['hardware_id'])
            || isset($details['node_id'])
        ) {
            return true;
        }

        return str_starts_with($code, 'node_error_') || $code === 'node_error';
    }

    private function fallbackTitle(string $code): string
    {
        if ($code === '' || $code === 'unknown_alert') {
            return 'Неизвестный алерт';
        }

        if (str_starts_with($code, 'node_error_') || $code === 'node_error') {
            return 'Ошибка узла';
        }

        if (str_starts_with($code, 'infra_')) {
            return 'Инфраструктурная ошибка';
        }

        if (str_starts_with($code, 'biz_')) {
            return 'Бизнес-алерт';
        }

        return 'Системное предупреждение';
    }

    private function normalizeSource(mixed $value): ?string
    {
        if (! is_string($value)) {
            return null;
        }

        $normalized = strtolower(trim($value));

        return in_array($normalized, ['biz', 'infra', 'node'], true)
            ? $normalized
            : null;
    }

    private function normalizeSeverityValue(mixed $value): ?string
    {
        if (! is_string($value)) {
            return null;
        }

        $normalized = strtolower(trim($value));

        return in_array($normalized, ['info', 'warning', 'error', 'critical'], true)
            ? $normalized
            : null;
    }

    private function normalizeCategory(mixed $value): ?string
    {
        if (! is_string($value)) {
            return null;
        }

        $normalized = strtolower(trim($value));

        return in_array(
            $normalized,
            ['agronomy', 'infrastructure', 'operations', 'node', 'config', 'safety', 'other'],
            true
        ) ? $normalized : null;
    }
}
