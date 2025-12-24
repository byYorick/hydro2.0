<?php

namespace App\Policies;

use App\Models\User;
use App\Models\Zone;
use App\Helpers\ZoneAccessHelper;

class ZonePolicy
{
    /**
     * Determine whether the user can view any models.
     */
    public function viewAny(User $user): bool
    {
        return true; // Все авторизованные пользователи могут видеть список
    }

    /**
     * Determine whether the user can view the model.
     */
    public function view(User $user, Zone $zone): bool
    {
        return ZoneAccessHelper::canAccessZone($user, $zone->id);
    }

    /**
     * Determine whether the user can create models.
     */
    public function create(User $user): bool
    {
        // Требуется роль operator или выше
        return in_array($user->role, ['operator', 'admin', 'agronomist', 'engineer']);
    }

    /**
     * Determine whether the user can update the model.
     */
    public function update(User $user, Zone $zone): bool
    {
        if (!ZoneAccessHelper::canAccessZone($user, $zone->id)) {
            return false;
        }
        
        // Требуется роль operator или выше
        return in_array($user->role, ['operator', 'admin', 'agronomist', 'engineer']);
    }

    /**
     * Determine whether the user can delete the model.
     */
    public function delete(User $user, Zone $zone): bool
    {
        if (!ZoneAccessHelper::canAccessZone($user, $zone->id)) {
            return false;
        }
        
        // Требуется роль admin
        return $user->isAdmin();
    }

    /**
     * Determine whether the user can send commands to the zone.
     */
    public function sendCommand(User $user, Zone $zone): bool
    {
        if (!ZoneAccessHelper::canAccessZone($user, $zone->id)) {
            return false;
        }
        
        // Требуется роль operator или выше
        return in_array($user->role, ['operator', 'admin', 'agronomist', 'engineer']);
    }
}

