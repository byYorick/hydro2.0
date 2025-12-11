<?php

namespace App\Policies;

use App\Models\User;
use App\Models\Command;
use App\Models\Zone;
use App\Models\DeviceNode;
use App\Helpers\ZoneAccessHelper;

class CommandPolicy
{
    /**
     * Determine whether the user can view any models.
     */
    public function viewAny(User $user): bool
    {
        return true; // Все авторизованные пользователи могут видеть список команд
    }

    /**
     * Determine whether the user can view the model.
     */
    public function view(User $user, Command $command): bool
    {
        // Проверяем доступ к зоне команды
        if ($command->zone_id) {
            return ZoneAccessHelper::canAccessZone($user, $command->zone_id);
        }
        
        // Если команда привязана к узлу, проверяем доступ к узлу
        if ($command->node_id) {
            $node = DeviceNode::find($command->node_id);
            if ($node) {
                return ZoneAccessHelper::canAccessNode($user, $node);
            }
        }
        
        return false;
    }

    /**
     * Determine whether the user can create models.
     */
    public function create(User $user, ?Zone $zone = null, ?DeviceNode $node = null): bool
    {
        // Для команд зоны
        if ($zone) {
            if (!ZoneAccessHelper::canAccessZone($user, $zone->id)) {
                return false;
            }
        }
        
        // Для команд узла
        if ($node) {
            if (!ZoneAccessHelper::canAccessNode($user, $node)) {
                return false;
            }
        }
        
        // Требуется роль operator или выше
        return in_array($user->role, ['operator', 'admin', 'agronomist', 'engineer']);
    }

    /**
     * Determine whether the user can update the model.
     */
    public function update(User $user, Command $command): bool
    {
        // Команды обычно не обновляются, но если нужно - проверяем доступ
        if ($command->zone_id) {
            if (!ZoneAccessHelper::canAccessZone($user, $command->zone_id)) {
                return false;
            }
        }
        
        // Требуется роль operator или выше
        return in_array($user->role, ['operator', 'admin', 'agronomist', 'engineer']);
    }

    /**
     * Determine whether the user can delete the model.
     */
    public function delete(User $user, Command $command): bool
    {
        // Команды обычно не удаляются, но если нужно - проверяем доступ
        if ($command->zone_id) {
            if (!ZoneAccessHelper::canAccessZone($user, $command->zone_id)) {
                return false;
            }
        }
        
        // Требуется роль admin
        return $user->isAdmin();
    }
}

