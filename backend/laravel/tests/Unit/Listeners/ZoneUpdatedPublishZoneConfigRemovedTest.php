<?php

namespace Tests\Unit\Listeners;

use App\Events\NodeConfigUpdated;
use App\Events\ZoneUpdated;
use App\Listeners\PublishNodeConfigOnUpdate;
use App\Services\PythonBridgeService;
use Illuminate\Support\Facades\Event;
use Tests\TestCase;

class ZoneUpdatedPublishZoneConfigRemovedTest extends TestCase
{
    public function test_publish_zone_config_update_listener_class_is_removed(): void
    {
        $this->assertFileDoesNotExist(app_path('Listeners/PublishZoneConfigUpdate.php'));
        $this->assertFalse(
            class_exists(\App\Listeners\PublishZoneConfigUpdate::class, false)
        );
    }

    public function test_python_bridge_notify_config_update_method_is_removed(): void
    {
        $this->assertFalse(method_exists(PythonBridgeService::class, 'notifyConfigUpdate'));
    }

    public function test_zone_updated_does_not_listen_for_publish_zone_config_update(): void
    {
        $matched = false;
        foreach ($this->listenersFor(ZoneUpdated::class) as $listener) {
            if ($this->listenerRefersTo($listener, 'PublishZoneConfigUpdate')) {
                $matched = true;
                break;
            }
        }

        $this->assertFalse($matched, 'ZoneUpdated не должен регистрировать PublishZoneConfigUpdate');
    }

    public function test_node_config_updated_still_listens_for_publish_node_config_on_update(): void
    {
        $listeners = $this->listenersFor(NodeConfigUpdated::class);

        $this->assertTrue(
            collect($listeners)->contains(
                fn (mixed $listener): bool => $this->listenerRefersTo($listener, PublishNodeConfigOnUpdate::class)
            ),
            'PublishNodeConfigOnUpdate должен остаться зарегистрированным'
        );
    }

    /**
     * @return list<mixed>
     */
    private function listenersFor(string $event): array
    {
        $raw = Event::getRawListeners();

        return $raw[$event] ?? [];
    }

    private function listenerRefersTo(mixed $listener, string $needle): bool
    {
        if (is_string($listener)) {
            return $listener === $needle || str_contains($listener, $needle);
        }

        if (is_array($listener) && isset($listener[0]) && is_string($listener[0])) {
            return $listener[0] === $needle || str_contains($listener[0], $needle);
        }

        return false;
    }
}
