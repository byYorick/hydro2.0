<?php

namespace App\Support\Automation;

use Carbon\CarbonInterface;

final class ZoneLogicProfile
{
    /**
     * @param  array<string, mixed>  $subsystems
     * @param  array<string, mixed>  $commandPlans
     */
    public function __construct(
        public readonly ?int $id,
        public readonly int $zoneId,
        public readonly string $mode,
        public readonly array $subsystems,
        public readonly array $commandPlans,
        public readonly bool $isActive,
        public readonly ?int $createdBy,
        public readonly ?int $updatedBy,
        public readonly ?CarbonInterface $createdAt,
        public readonly ?CarbonInterface $updatedAt,
    ) {
    }
}
