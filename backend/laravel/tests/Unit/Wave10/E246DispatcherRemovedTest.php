<?php

namespace Tests\Unit\Wave10;

use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Route;
use Tests\TestCase;

class E246DispatcherRemovedTest extends TestCase
{
    public function test_e246_dispatch_schedules_command_removed(): void
    {
        $this->assertFileDoesNotExist(
            app_path('Services/AutomationScheduler/ScheduleDispatcher.php'),
            'ScheduleDispatcher must be deleted',
        );
        $this->assertFileDoesNotExist(
            app_path('Console/Commands/AutomationDispatchSchedules.php'),
            'AutomationDispatchSchedules command class must be deleted',
        );

        $exit = Artisan::call('list');
        $this->assertSame(0, $exit);
        $output = Artisan::output();
        $this->assertStringNotContainsString('automation:dispatch-schedules', $output);

        $routes = collect(Route::getRoutes())->map(
            fn ($route) => $route->uri()
        )->implode("\n");
        foreach ([
            'zones/{zone}/start-irrigation',
            'zones/{zone}/start-lighting-tick',
            'zones/{zone}/start-solution-topup',
        ] as $uri) {
            $this->assertStringNotContainsString($uri, $routes, "route {$uri} must be gone");
        }
    }
}
