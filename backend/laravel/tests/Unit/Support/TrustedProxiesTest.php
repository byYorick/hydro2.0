<?php

namespace Tests\Unit\Support;

use App\Support\TrustedProxies;
use PHPUnit\Framework\TestCase;

class TrustedProxiesTest extends TestCase
{
    public function test_missing_value_uses_docker_private_ranges(): void
    {
        $this->assertSame(TrustedProxies::DEFAULT, TrustedProxies::resolve(null));
    }

    public function test_empty_value_trusts_nobody(): void
    {
        $this->assertSame([], TrustedProxies::resolve(''));
        $this->assertSame([], TrustedProxies::resolve('   '));
    }

    public function test_star_is_explicit_opt_in(): void
    {
        $this->assertSame('*', TrustedProxies::resolve('*'));
        $this->assertSame('*', TrustedProxies::resolve(' * '));
    }

    public function test_comma_list_is_trimmed(): void
    {
        $this->assertSame(
            ['10.1.0.0/16', '192.168.50.2'],
            TrustedProxies::resolve(' 10.1.0.0/16, , 192.168.50.2 '),
        );
    }
}
