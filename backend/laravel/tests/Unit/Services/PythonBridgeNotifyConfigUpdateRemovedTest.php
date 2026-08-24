<?php

namespace Tests\Unit\Services;

use App\Services\PythonBridgeService;
use Tests\TestCase;

class PythonBridgeNotifyConfigUpdateRemovedTest extends TestCase
{
    public function test_notify_config_update_method_is_removed(): void
    {
        $this->assertFalse(
            method_exists(PythonBridgeService::class, 'notifyConfigUpdate'),
            'notifyConfigUpdate удалён: эндпоинта /bridge/config/zone-updated нет, AE3 читает SQL read-model'
        );
    }
}
