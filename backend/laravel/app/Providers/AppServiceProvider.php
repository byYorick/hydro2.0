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
use Illuminate\Cache\RateLimiting\Limit;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\RateLimiter;
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
        if ($this->app->environment(['testing', 'e2e'])) {
            Vite::useHotFile(storage_path('framework/vite.hot'));
        }

        Vite::prefetch(concurrency: 3);

        // Регистрация одной ноды может ретраиться, а несколько нод приходят через один bridge IP.
        // Поэтому держим жёсткий лимит на identity узла и отдельный burst-лимит на IP.
        RateLimiter::for('node_register', function (Request $request) {
            $identity = trim((string) (
                $request->input('node_uid')
                ?: $request->input('hardware_id')
                ?: $request->input('uid')
                ?: 'unknown'
            ));
            $ip = (string) $request->ip();
            $limitResponse = static function ($request, array $headers) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'RATE_LIMIT_EXCEEDED',
                    'message' => 'Too many node registration attempts. Please try again later.',
                ], 429)->withHeaders($headers);
            };

            return [
                Limit::perMinute(120)
                    ->by("node_register:ip:{$ip}")
                    ->response($limitResponse),
                Limit::perMinute(10)
                    ->by("node_register:identity:{$ip}:{$identity}")
                    ->response($limitResponse),
            ];
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
