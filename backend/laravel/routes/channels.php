<?php

use Illuminate\Support\Facades\Broadcast;

// Канал для обновлений зон
Broadcast::channel('hydro.zones.{zoneId}', function ($user, $zoneId) {
    return $user !== null; // viewer+ могут слушать
});

// Канал для команд зоны (приватный)
Broadcast::channel('commands.{zoneId}', function ($user, $zoneId) {
    return $user !== null; // viewer+ могут слушать статусы команд
});

// Канал для глобальных событий (публичный)
// Не требует авторизации, так как это публичный канал

