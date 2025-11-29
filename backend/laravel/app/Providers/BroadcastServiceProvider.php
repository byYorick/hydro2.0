<?php

namespace App\Providers;

use Illuminate\Support\Facades\Broadcast;
use Illuminate\Support\ServiceProvider;

class BroadcastServiceProvider extends ServiceProvider
{
    public function boot(): void
    {
        // Custom /broadcasting/auth route is defined in routes/web.php
        require base_path('routes/channels.php');
    }
}
