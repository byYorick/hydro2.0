<?php

namespace App\Policies;

use App\Models\DeviceNode;
use App\Models\User;
use App\Helpers\ZoneAccessHelper;

class DeviceNodePolicy
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
    public function view(User $user, DeviceNode $deviceNode): bool
    {
        return ZoneAccessHelper::canAccessNode($user, $deviceNode);
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
    public function update(User $user, DeviceNode $deviceNode): bool
    {
        if (!ZoneAccessHelper::canAccessNode($user, $deviceNode)) {
            return false;
        }
        
        // Требуется роль operator или выше
        return in_array($user->role, ['operator', 'admin', 'agronomist', 'engineer']);
    }

    /**
     * Determine whether the user can delete the model.
     */
    public function delete(User $user, DeviceNode $deviceNode): bool
    {
        if (!ZoneAccessHelper::canAccessNode($user, $deviceNode)) {
            return false;
        }
        
        // Требуется роль operator или выше
        return in_array($user->role, ['operator', 'admin', 'agronomist', 'engineer']);
    }

    /**
     * Determine whether the user can detach the node from zone.
     */
    public function detach(User $user, DeviceNode $deviceNode): bool
    {
        if (!ZoneAccessHelper::canAccessNode($user, $deviceNode)) {
            return false;
        }
        
        // Требуется роль operator или выше
        return in_array($user->role, ['operator', 'admin', 'agronomist', 'engineer']);
    }

    /**
     * Determine whether the user can publish config for the node.
     */
    public function publishConfig(User $user, DeviceNode $deviceNode): bool
    {
        if (!ZoneAccessHelper::canAccessNode($user, $deviceNode)) {
            return false;
        }
        
        // Требуется роль operator или выше
        return in_array($user->role, ['operator', 'admin', 'agronomist', 'engineer']);
    }

    /**
     * Determine whether the user can send commands to the node.
     */
    public function sendCommand(User $user, DeviceNode $deviceNode): bool
    {
        if (!ZoneAccessHelper::canAccessNode($user, $deviceNode)) {
            return false;
        }
        
        // Требуется роль operator или выше
        return in_array($user->role, ['operator', 'admin', 'agronomist', 'engineer']);
    }
}
