<?php

namespace App\Policies;

use App\Models\User;
use App\Models\GrowCycle;
use App\Models\Zone;

class GrowCyclePolicy
{
    /**
     * Определить, может ли пользователь управлять циклами (создавать, останавливать, менять фазы)
     */
    public function manage(User $user): bool
    {
        return $user->role === 'agronomist';
    }

    /**
     * Определить, может ли пользователь создать цикл в зоне
     */
    public function create(User $user, Zone $zone): bool
    {
        return $user->role === 'agronomist';
    }

    /**
     * Определить, может ли пользователь обновить цикл (pause, resume, harvest, abort, change phase)
     */
    public function update(User $user, GrowCycle $growCycle): bool
    {
        return $user->role === 'agronomist';
    }

    /**
     * Определить, может ли пользователь просматривать цикл
     */
    public function view(User $user, GrowCycle $growCycle): bool
    {
        // Все авторизованные пользователи могут просматривать
        return true;
    }

    /**
     * Определить, может ли пользователь вручную переключать фазы
     */
    public function switchPhase(User $user, GrowCycle $growCycle): bool
    {
        return $user->role === 'agronomist';
    }

    /**
     * Определить, может ли пользователь менять ревизию рецепта в цикле
     */
    public function changeRecipeRevision(User $user, GrowCycle $growCycle): bool
    {
        return $user->role === 'agronomist';
    }
}

