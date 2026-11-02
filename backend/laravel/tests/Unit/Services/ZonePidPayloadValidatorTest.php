<?php

namespace Tests\Unit\Services;

use App\Services\ZonePidPayloadValidator;
use InvalidArgumentException;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class ZonePidPayloadValidatorTest extends TestCase
{
    private static function validPayload(): array
    {
        return [
            'dead_zone' => 0.05, 'close_zone' => 0.3, 'far_zone' => 1.0,
            'zone_coeffs' => ['close' => ['kp' => 5.0, 'ki' => 0.05, 'kd' => 0.0],
                'far' => ['kp' => 8.0, 'ki' => 0.02, 'kd' => 0.0]],
            'max_integral' => 20.0,
        ];
    }

    public function test_schema_boundary_values_are_accepted(): void
    {
        $payload = self::validPayload();
        $payload['dead_zone'] = 10;
        $payload['close_zone'] = 20;
        $payload['far_zone'] = 50;
        $payload['max_integral'] = 500;
        $payload['zone_coeffs']['far'] = ['kp' => 1000, 'ki' => 100, 'kd' => 100];
        ZonePidPayloadValidator::validate($payload, 'ph');
        ZonePidPayloadValidator::validate($payload, 'ec');
        $this->addToAssertionCount(2);
    }

    #[DataProvider('invalidPayloads')]
    public function test_rejects_values_outside_canonical_schema(array $payload): void
    {
        $this->expectException(InvalidArgumentException::class);
        ZonePidPayloadValidator::validate($payload, 'ph');
    }

    public static function invalidPayloads(): iterable
    {
        foreach (['dead_zone' => [-1, 0, 10.1, '0.05', null, true, NAN, INF],
            'close_zone' => [-1, 20.1, 'wrong'], 'far_zone' => [-1, 50.1],
            'max_integral' => [0, -1, 500.1, '20']] as $key => $values) {
            foreach ($values as $index => $value) {
                yield "{$key}-{$index}" => [array_replace(self::validPayload(), [$key => $value])];
            }
        }
        foreach (['close_zone' => 0.05, 'far_zone' => 0.3] as $key => $value) {
            yield "unordered-{$key}" => [array_replace(self::validPayload(), [$key => $value])];
        }
        foreach (['kp' => [-1, 1000.1], 'ki' => [-1, 100.1], 'kd' => [-1, 100.1]] as $key => $values) {
            foreach ($values as $index => $value) {
                $payload = self::validPayload();
                $payload['zone_coeffs']['close'][$key] = $value;
                yield "gain-{$key}-{$index}" => [$payload];
            }
        }
        $payload = self::validPayload();
        $payload['zone_coeffs']['extra'] = [];
        yield 'unknown-zone' => [$payload];
        $payload = self::validPayload();
        $payload['zone_coeffs']['close']['extra'] = 1;
        yield 'unknown-gain' => [$payload];
        $payload = self::validPayload();
        unset($payload['zone_coeffs']['close']['kp']);
        yield 'missing-gain' => [$payload];
    }
}
