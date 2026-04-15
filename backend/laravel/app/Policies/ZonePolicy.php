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

    /**
     * Determine whether the user can switch zone into config_mode='live'.
     *
     * Live mode allows hot-reloading zone.correction and recipe.phase
     * parameters while a cycle is running — only agronomist/engineer/admin
     * are qualified to make such tuning decisions (Phase 5 spec Q2).
     */
    public function setLive(User $user, Zone $zone): bool
    {
        if (!ZoneAccessHelper::canAccessZone($user, $zone->id)) {
            return false;
        }

        return in_array($user->role, ['agronomist', 'engineer', 'admin']);
    }
}

