<?php

namespace App\Support\Automation;

use App\Models\AutomationConfigPreset;
use Carbon\CarbonInterface;

final class ZoneCorrectionConfiguration
{
    /**
     * @param  array<string, mixed>  $baseConfig
     * @param  array<string, mixed>  $phaseOverrides
     * @param  array<string, mixed>  $resolvedConfig
     */
    public function __construct(
        public readonly ?int $id,
        public readonly int $zoneId,
        public readonly ?int $presetId,
        public readonly ?AutomationConfigPreset $preset,
        public readonly array $baseConfig,
        public readonly array $phaseOverrides,
        public readonly array $resolvedConfig,
        public readonly int $version,
        public readonly ?int $updatedBy,
        public readonly ?CarbonInterface $updatedAt,
        public readonly ?CarbonInterface $lastAppliedAt,
        public readonly ?int $lastAppliedVersion,
    ) {
    }
}
