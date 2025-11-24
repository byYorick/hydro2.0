<?php

namespace App\Providers;

use Illuminate\Support\Facades\Vite;
use Illuminate\Support\ServiceProvider;
use Illuminate\Support\Facades\Event;
use App\Events\ZoneUpdated;
use App\Listeners\PublishZoneConfigUpdate;
use App\Events\NodeConfigUpdated;
use App\Listeners\PublishNodeConfigOnUpdate;
use App\Models\Command;
use App\Observers\CommandObserver;
use App\Models\ZoneEvent;
use App\Observers\ZoneEventObserver;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register any application services.
     */
    public function register(): void
    {
        // Регистрация DigitalTwinClient
        $this->app->singleton(\App\Services\DigitalTwinClient::class, function ($app) {
            $baseUrl = config('services.digital_twin.url', 'http://digital-twin:8003');
            return new \App\Services\DigitalTwinClient($baseUrl);
        });
    }

    /**
     * Bootstrap any application services.
     */
    public function boot(): void
    {
        Vite::prefetch(concurrency: 3);
        
        // Регистрация слушателей событий
        Event::listen(
            ZoneUpdated::class,
            PublishZoneConfigUpdate::class
        );
        
        Event::listen(
            NodeConfigUpdated::class,
            PublishNodeConfigOnUpdate::class
        );
        
        // Регистрация Observer для Command
        Command::observe(CommandObserver::class);
        
        // Регистрация Observer для ZoneEvent
        ZoneEvent::observe(ZoneEventObserver::class);
    }
}
