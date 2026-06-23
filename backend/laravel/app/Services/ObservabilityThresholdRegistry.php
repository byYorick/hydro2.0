<?php

namespace App\Services;

use App\Support\Automation\ObservabilityThresholdsCatalog;

class ObservabilityThresholdRegistry
{
    public function __construct(
        private readonly AutomationConfigDocumentService $documents,
    ) {}

    /**
     * @return array<string, int>
     */
    public function resolved(): array
    {
        $payload = $this->documents->getSystemPayloadByLegacyNamespace(
            ObservabilityThresholdsCatalog::NAMESPACE_KEY,
        );

        return SystemAutomationSettingsCatalog::merge(
            ObservabilityThresholdsCatalog::defaults(),
            $payload,
        );
    }

    public function int(string $key, int $fallback): int
    {
        $value = $this->resolved()[$key] ?? $fallback;

        return max(0, (int) $value);
    }

    /**
     * @return array{warn:int, critical:int}|null
     */
    public function stageElapsed(string $stage): ?array
    {
        $normalized = strtolower(trim($stage));
        if ($normalized === '' || ! array_key_exists($normalized, ObservabilityThresholdsCatalog::stageKeys())) {
            return null;
        }

        return [
            'warn' => $this->int("stage_{$normalized}_warn_sec", 300),
            'critical' => $this->int("stage_{$normalized}_critical_sec", 1800),
        ];
    }
}
