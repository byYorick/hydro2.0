<?php

namespace App\Observers;

use App\Models\Greenhouse;
use App\Services\AccessControlAssignmentService;

class GreenhouseObserver
{
    public function created(Greenhouse $greenhouse): void
    {
        app(AccessControlAssignmentService::class)->assignGreenhouseToAllNonAdminUsers($greenhouse);
    }
}
