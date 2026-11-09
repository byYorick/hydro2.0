<?php

namespace Tests\Feature;

use Illuminate\Contracts\Http\Kernel;
use Illuminate\Http\Request;
use Tests\TestCase;

class TrustedProxiesTest extends TestCase
{
    public function test_public_client_cannot_spoof_forwarded_for(): void
    {
        $request = Request::create('/up', 'GET');
        $request->server->set('REMOTE_ADDR', '203.0.113.10');
        $request->headers->set('X-Forwarded-For', '198.51.100.20');

        $this->app->make(Kernel::class)->handle($request);

        $this->assertSame('203.0.113.10', $request->ip());
    }

    public function test_docker_network_proxy_sets_client_ip_from_forwarded_for(): void
    {
        $request = Request::create('/up', 'GET');
        $request->server->set('REMOTE_ADDR', '172.18.0.5');
        $request->headers->set('X-Forwarded-For', '198.51.100.20');

        $this->app->make(Kernel::class)->handle($request);

        $this->assertSame('198.51.100.20', $request->ip());
    }
}
