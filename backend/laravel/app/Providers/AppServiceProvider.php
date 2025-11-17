<?php

namespace App\Providers;

use Illuminate\Support\Facades\Vite;
use Illuminate\Support\ServiceProvider;
use Illuminate\Support\Facades\Event;
use App\Events\ZoneUpdated;
use App\Listeners\PublishZoneConfigUpdate;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register any application services.
     */
    public function register(): void
    {
        //
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
    }
}
