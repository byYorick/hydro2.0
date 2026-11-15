<?php

namespace App\Policies;

use App\Models\Plant;
use App\Models\User;

class PlantPolicy
{
    /**
     * Роли, которым разрешено менять каталог культур.
     * viewer остаётся только на чтение.
     */
    private const WRITE_ROLES = ['admin', 'operator', 'agronomist', 'engineer'];

    public function viewAny(User $user): bool
    {
        return true;
    }

    public function view(User $user, Plant $plant): bool
    {
        return true;
    }

    public function create(User $user): bool
    {
        return $this->canWrite($user);
    }

    public function update(User $user, Plant $plant): bool
    {
        return $this->canWrite($user);
    }

    public function delete(User $user, Plant $plant): bool
    {
        return $this->canWrite($user);
    }

    public function manage(User $user): bool
    {
        return $this->canWrite($user);
    }

    private function canWrite(User $user): bool
    {
        return in_array($user->role, self::WRITE_ROLES, true);
    }
}
