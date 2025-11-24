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

// Канал для глобальных команд (приватный)
Broadcast::channel('commands.global', function ($user) {
    return $user !== null; // viewer+ могут слушать статусы команд
});

// Канал для глобальных событий (публичный)
// Не требует авторизации, так как это публичный канал

// Канал для обновлений устройств (публичный, но требует авторизации)
Broadcast::channel('hydro.devices', function ($user) {
    return $user !== null; // Требует авторизации
});

