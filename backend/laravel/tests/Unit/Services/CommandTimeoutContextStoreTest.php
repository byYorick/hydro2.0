<?php

namespace Tests\Unit\Services;

use App\Services\CommandTimeoutContextStore;
use Tests\TestCase;

class CommandTimeoutContextStoreTest extends TestCase
{
    public function test_put_and_pull_returns_context_once(): void
    {
        $store = new CommandTimeoutContextStore;
        $store->put(42, ['node_uid' => 'nd-1', 'channel' => 'pump_main']);

        $this->assertSame(['node_uid' => 'nd-1', 'channel' => 'pump_main'], $store->pull(42));
        $this->assertSame([], $store->pull(42));
    }
}
