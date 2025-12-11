<?php

namespace App\Providers;

use App\Events\NodeConfigUpdated;
use App\Events\ZoneUpdated;
use App\Listeners\PublishNodeConfigOnUpdate;
use App\Listeners\PublishZoneConfigUpdate;
use App\Models\Command;
use App\Models\ZoneEvent;
use App\Observers\CommandObserver;
use App\Observers\ZoneEventObserver;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\Vite;
use Illuminate\Support\ServiceProvider;

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
        
        // Настройка rate limiting для регистрации нод
        // Более строгий лимит: 10 запросов в минуту по IP
        \Illuminate\Support\Facades\RateLimiter::for('node_register', function (\Illuminate\Http\Request $request) {
            return \Illuminate\Cache\RateLimiting\Limit::perMinute(10)
                ->by($request->ip())
                ->response(function ($request, array $headers) {
                    return response()->json([
                        'status' => 'error',
                        'code' => 'RATE_LIMIT_EXCEEDED',
                        'message' => 'Too many node registration attempts. Please try again later.',
                    ], 429)->withHeaders($headers);
                });
        });
        
        // Регистрация слушателей событий
        Event::listen(
            ZoneUpdated::class,
            PublishZoneConfigUpdate::class
        );
        
        // Регистрируем listener с afterCommit, чтобы он выполнялся после коммита транзакции
        // Это предотвращает блокировку БД при зависании history-logger
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
