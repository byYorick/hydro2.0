<?php

namespace App\Observers;

use App\Models\Zone;
use App\Services\AccessControlAssignmentService;

class ZoneObserver
{
    public function created(Zone $zone): void
    {
        app(AccessControlAssignmentService::class)->assignZoneToAllNonAdminUsers($zone);
    }
}
