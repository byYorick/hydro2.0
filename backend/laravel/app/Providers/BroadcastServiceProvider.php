<?php

namespace App\Providers;

use Illuminate\Support\Facades\Broadcast;
use Illuminate\Support\ServiceProvider;

class BroadcastServiceProvider extends ServiceProvider
{
    public function boot(): void
    {
        // ИСПРАВЛЕНО: Убрано Broadcast::routes() для предотвращения дублирования маршрута /broadcasting/auth
        // Кастомный маршрут с throttle определен в routes/web.php
        // Два маршрута на один путь с разными правилами вызывали непредсказуемые ответы (403/429/500)
        // Broadcast::routes([
        //     'middleware' => [
        //         'web',
        //         'auth',
        //         'throttle:60,1',
        //     ],
        // ]);

        require base_path('routes/channels.php');
    }
}
