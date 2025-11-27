<?php

namespace App\Providers;

use Illuminate\Support\Facades\Broadcast;
use Illuminate\Support\ServiceProvider;

class BroadcastServiceProvider extends ServiceProvider
{
    public function boot(): void
    {
        Broadcast::routes([
            'middleware' => [
                'web',
                'auth:sanctum',
                'throttle:60,1',
            ],
        ]);

        require base_path('routes/channels.php');
    }
}
