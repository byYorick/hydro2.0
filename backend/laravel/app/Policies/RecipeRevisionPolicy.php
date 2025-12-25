<?php

namespace App\Policies;

use App\Models\User;
use App\Models\RecipeRevision;

class RecipeRevisionPolicy
{
    /**
     * Определить, может ли пользователь редактировать рецепты и публиковать ревизии
     */
    public function manage(User $user): bool
    {
        return $user->role === 'agronomist';
    }

    /**
     * Определить, может ли пользователь создать ревизию
     */
    public function create(User $user): bool
    {
        return $user->role === 'agronomist';
    }

    /**
     * Определить, может ли пользователь обновить ревизию (только DRAFT)
     */
    public function update(User $user, RecipeRevision $recipeRevision): bool
    {
        if ($user->role !== 'agronomist') {
            return false;
        }

        // Только черновики можно редактировать
        return $recipeRevision->status === 'DRAFT';
    }

    /**
     * Определить, может ли пользователь опубликовать ревизию
     */
    public function publish(User $user, RecipeRevision $recipeRevision): bool
    {
        if ($user->role !== 'agronomist') {
            return false;
        }

        // Только черновики можно публиковать
        return $recipeRevision->status === 'DRAFT';
    }

    /**
     * Определить, может ли пользователь просматривать ревизию
     */
    public function view(User $user, RecipeRevision $recipeRevision): bool
    {
        // Все авторизованные пользователи могут просматривать
        return true;
    }
}

