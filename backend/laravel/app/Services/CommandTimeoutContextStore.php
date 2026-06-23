<?php

namespace App\Services;

/**
 * Временный контекст scheduler-таймаута для обогащения command_status в observer.
 */
class CommandTimeoutContextStore
{
    /** @var array<int, array<string, mixed>> */
    private array $contextByCommandId = [];

    /**
     * @param  array<string, mixed>  $context
     */
    public function put(int $commandId, array $context): void
    {
        $this->contextByCommandId[$commandId] = $context;
    }

    /**
     * @return array<string, mixed>
     */
    public function pull(int $commandId): array
    {
        $context = $this->contextByCommandId[$commandId] ?? [];
        unset($this->contextByCommandId[$commandId]);

        return $context;
    }
}
