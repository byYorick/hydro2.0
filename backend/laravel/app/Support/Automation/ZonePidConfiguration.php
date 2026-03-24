<?php

namespace App\Support\Automation;

final class ZonePidConfiguration
{
    /**
     * @param  array<string, mixed>  $config
     */
    public function __construct(
        public readonly ?int $id,
        public readonly int $zoneId,
        public readonly string $type,
        public readonly array $config,
        public readonly ?int $updatedBy,
        public readonly mixed $updatedAt,
    ) {
    }
}
