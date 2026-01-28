<?php

namespace App\Enums;

enum ZoneStatus: string
{
    case ONLINE = 'online';
    case OFFLINE = 'offline';
    case WARNING = 'warning';
    case CRITICAL = 'critical';
}
