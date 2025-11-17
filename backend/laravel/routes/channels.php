<?php

use Illuminate\Support\Facades\Broadcast;

Broadcast::channel('hydro.zones.{zoneId}', function ($user, $zoneId) {
    return $user !== null; // viewer+ могут слушать
});

