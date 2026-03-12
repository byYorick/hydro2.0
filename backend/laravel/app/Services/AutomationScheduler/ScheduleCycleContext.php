<?php

namespace App\Services\AutomationScheduler;

use Carbon\CarbonImmutable;

final class ScheduleCycleContext
{
    /**
     * @param  array<string, mixed>  $cfg
     * @param  array<string, string>  $headers
     * @param  array<string, CarbonImmutable>  $lastRunByTaskName
     * @param  array<string, bool>  $reconciledBusyness
     */
    public function __construct(
        public readonly array $cfg,
        public readonly array $headers,
        public readonly string $traceId,
        public readonly CarbonImmutable $cycleNow,
        public readonly array $lastRunByTaskName,
        public readonly array $reconciledBusyness,
    ) {}
}
