<?php

namespace App\Services;

use App\Models\SystemLog;
use App\Models\User;
use App\Models\ZoneEvent;

/**
 * Журнал safety-решений: кто, когда, зона, действие, результат.
 * Подписи, HMAC-секреты и токены в payload не попадают.
 */
class SafetyAuditLogger
{
    /**
     * @param  array<string, mixed>  $context
     */
    public function write(
        string $action,
        int $zoneId,
        string $result,
        array $context = [],
        ?User $user = null,
        bool $zoneEvent = false,
        ?string $zoneEventType = null,
    ): void {
        $safe = $this->redact($context);
        $recordedAt = now();

        SystemLog::query()->create([
            'level' => $this->levelFor($result),
            'message' => $action,
            'context' => [
                'service' => 'laravel',
                'action' => $action,
                'zone_id' => $zoneId,
                'result' => $result,
                'user_id' => $user?->id,
                'user_name' => $user?->name,
                'at' => $recordedAt->toIso8601String(),
                'details' => $safe,
            ],
            'created_at' => $recordedAt,
        ]);

        if ($zoneEvent && $zoneId > 0 && is_string($zoneEventType) && $zoneEventType !== '') {
            ZoneEvent::query()->create([
                'zone_id' => $zoneId,
                'type' => $zoneEventType,
                'payload_json' => array_merge($safe, [
                    'action' => $action,
                    'result' => $result,
                    'user_id' => $user?->id,
                    'user_name' => $user?->name,
                ]),
                'created_at' => $recordedAt,
            ]);
        }
    }

    /**
     * @param  array<string, mixed>  $payload
     * @return array<string, mixed>
     */
    public function redact(array $payload): array
    {
        $clean = [];
        foreach ($payload as $key => $value) {
            $normalized = strtolower((string) $key);
            if ($this->isSensitiveKey($normalized)) {
                continue;
            }
            if (is_array($value)) {
                $clean[$key] = $this->redact($value);

                continue;
            }
            if (is_scalar($value) || $value === null) {
                $clean[$key] = $value;
            }
        }

        return $clean;
    }

    private function isSensitiveKey(string $key): bool
    {
        foreach (['sig', 'signature', 'secret', 'token', 'password', 'authorization', 'hmac', 'node_secret'] as $needle) {
            if ($key === $needle || str_contains($key, $needle)) {
                return true;
            }
        }

        return false;
    }

    private function levelFor(string $result): string
    {
        return str_contains($result, 'reject') || str_contains($result, 'denied')
            ? 'warning'
            : 'info';
    }
}
