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

        $this->app->singleton(\App\Services\NodeSimManagerClient::class, function ($app) {
            $config = config('services.node_sim_manager', []);
            $mqttDefaults = [
                'host' => $config['mqtt_host'] ?? 'mqtt',
                'port' => (int) ($config['mqtt_port'] ?? 1883),
                'username' => $config['mqtt_username'] ?? null,
                'password' => $config['mqtt_password'] ?? null,
                'tls' => (bool) ($config['mqtt_tls'] ?? false),
                'ca_certs' => $config['mqtt_ca_certs'] ?? null,
                'keepalive' => (int) ($config['mqtt_keepalive'] ?? 60),
            ];
            $telemetryDefaults = [
                'interval_seconds' => (float) ($config['telemetry_interval_seconds'] ?? 5.0),
                'heartbeat_interval_seconds' => (float) ($config['heartbeat_interval_seconds'] ?? 30.0),
                'status_interval_seconds' => (float) ($config['status_interval_seconds'] ?? 60.0),
            ];

            return new \App\Services\NodeSimManagerClient(
                $config['url'] ?? 'http://node-sim-manager:9100',
                $config['token'] ?? null,
                (int) ($config['timeout'] ?? 10),
                $mqttDefaults,
                $telemetryDefaults,
            );
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
