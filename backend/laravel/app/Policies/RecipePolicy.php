<?php

namespace App\Policies;

use App\Models\Recipe;
use App\Models\User;

class RecipePolicy
{
    /**
     * Совпадает с middleware мутаций рецептов.
     * viewer не входит в список и не может менять рецепт.
     */
    private const WRITE_ROLES = ['admin', 'operator', 'agronomist', 'engineer'];

    public function viewAny(User $user): bool
    {
        return true;
    }

    public function view(User $user, Recipe $recipe): bool
    {
        return true;
    }

    public function create(User $user): bool
    {
        return $this->canWrite($user);
    }

    public function update(User $user, Recipe $recipe): bool
    {
        return $this->canWrite($user);
    }

    public function delete(User $user, Recipe $recipe): bool
    {
        return $this->canWrite($user);
    }

    private function canWrite(User $user): bool
    {
        return in_array($user->role, self::WRITE_ROLES, true);
    }
}
