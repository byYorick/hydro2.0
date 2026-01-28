<?php

namespace App\Providers;

use App\Models\GrowCycle;
use App\Models\RecipeRevision;
use App\Policies\GrowCyclePolicy;
use App\Policies\RecipeRevisionPolicy;
use Illuminate\Foundation\Support\Providers\AuthServiceProvider as ServiceProvider;

class AuthServiceProvider extends ServiceProvider
{
    /**
     * The policy mappings for the application.
     *
     * @var array<class-string, class-string>
     */
    protected $policies = [
        GrowCycle::class => GrowCyclePolicy::class,
        RecipeRevision::class => RecipeRevisionPolicy::class,
    ];

    /**
     * Register any authentication / authorization services.
     */
    public function boot(): void
    {
        //
    }
}

