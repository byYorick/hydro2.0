<?php

namespace App\Observers;

use App\Models\User;
use App\Services\AccessControlAssignmentService;

class UserObserver
{
    public function created(User $user): void
    {
        app(AccessControlAssignmentService::class)->assignExistingTopologyToUser($user);
    }
}
