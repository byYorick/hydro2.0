<?php

namespace Tests\Unit;

use App\Services\Automation\RadiationSumDecisionValidator;
use InvalidArgumentException;
use PHPUnit\Framework\TestCase;

class RadiationSumDecisionValidatorTest extends TestCase
{
    public function test_accepts_strawberry_and_lettuce_defaults(): void
    {
        RadiationSumDecisionValidator::validate($this->decision([
            'threshold_par_mol_m2' => 1.3,
            'max_interval_sec' => 5400,
            'fallback_interval_sec' => 2700,
            'max_daily_volume_l' => 40,
            'plant_count' => 20,
            'irrigation_ml_per_sec' => 2,
        ]), 'decision');

        RadiationSumDecisionValidator::validate($this->decision([
            'crop' => 'lettuce',
            'threshold_par_mol_m2' => 1.0,
            'max_interval_sec' => 3600,
            'fallback_interval_sec' => 3600,
            'max_daily_volume_l' => 20,
            'plant_count' => 12,
            'irrigation_ml_per_sec' => 1.5,
        ]), 'decision');

        $this->assertTrue(true);
    }

    public function test_rejects_out_of_range_without_clamping(): void
    {
        $payload = $this->decision([
            'threshold_par_mol_m2' => 1.0,
            'min_interval_sec' => 600,
            'max_interval_sec' => 1200,
            'fallback_interval_sec' => 1200,
            'max_daily_volume_l' => 10,
        ]);

        try {
            RadiationSumDecisionValidator::validate($payload, 'decision');
            $this->fail('expected rejection');
        } catch (InvalidArgumentException $exception) {
            $this->assertStringContainsString('threshold_par_mol_m2', $exception->getMessage());
        }

        $this->assertSame(1.0, $payload['config']['threshold_par_mol_m2']);
        $this->assertSame(600, $payload['config']['min_interval_sec']);
    }

    public function test_rejects_missing_required_fields_and_max_not_above_min(): void
    {
        try {
            RadiationSumDecisionValidator::validate($this->decision([
                'threshold_par_mol_m2' => 1.3,
                'max_interval_sec' => 5400,
                'max_daily_volume_l' => 10,
            ]), 'decision');
            $this->fail('missing fallback must be rejected');
        } catch (InvalidArgumentException $exception) {
            $this->assertStringContainsString('fallback_interval_sec', $exception->getMessage());
        }

        foreach ([3599, 5401] as $maxInterval) {
            try {
                RadiationSumDecisionValidator::validate($this->decision([
                    'threshold_par_mol_m2' => 1.3,
                    'max_interval_sec' => $maxInterval,
                    'fallback_interval_sec' => 2700,
                    'max_daily_volume_l' => 10,
                    'plant_count' => 10,
                    'irrigation_ml_per_sec' => 2,
                ]), 'decision');
                $this->fail("max_interval_sec {$maxInterval} must be rejected");
            } catch (InvalidArgumentException $exception) {
                $this->assertStringContainsString('max_interval_sec', $exception->getMessage());
            }
        }

        $this->expectException(InvalidArgumentException::class);
        RadiationSumDecisionValidator::validate($this->decision([
            'threshold_par_mol_m2' => 1.3,
            'max_interval_sec' => 5400,
            'fallback_interval_sec' => 2700,
            'max_daily_volume_l' => 10,
            'irrigation_ml_per_sec' => 2,
        ]), 'decision');
    }

    /**
     * @param  array<string, mixed>  $config
     * @return array<string, mixed>
     */
    private function decision(array $config): array
    {
        return [
            'strategy' => 'radiation_sum_v1',
            'config' => $config,
        ];
    }
}
