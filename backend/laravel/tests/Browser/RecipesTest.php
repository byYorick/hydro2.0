<?php

namespace Tests\Browser;

use App\Models\Recipe;
use App\Models\User;
use Laravel\Dusk\Browser;
use Tests\DuskTestCase;

class RecipesTest extends DuskTestCase
{
    public function test_recipes_list_page_loads(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        Recipe::factory()->count(2)->create();

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/recipes')
                ->assertPathIs('/recipes');

            $component = $browser->script(
                'return JSON.parse(document.getElementById("app").dataset.page).component;'
            )[0] ?? null;

            $this->assertNotNull($component, 'Inertia component name should be resolved.');
            $this->assertStringStartsWith('Recipes', $component);
        });
    }

    public function test_recipe_detail_page_loads(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $recipe = Recipe::factory()->create();

        $this->browse(function (Browser $browser) use ($user, $recipe) {
            $browser->loginAs($user)
                ->visit("/recipes/{$recipe->id}")
                ->assertPathIs("/recipes/{$recipe->id}");

            $component = $browser->script(
                'return JSON.parse(document.getElementById("app").dataset.page).component;'
            )[0] ?? null;

            $this->assertNotNull($component, 'Inertia component name should be resolved.');
            $this->assertStringStartsWith('Recipes', $component);
        });
    }

    public function test_recipe_create_page_loads(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
            'role' => 'admin',
        ]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/recipes/create')
                ->assertPathIs('/recipes/create');

            $component = $browser->script(
                'return JSON.parse(document.getElementById("app").dataset.page).component;'
            )[0] ?? null;

            $this->assertNotNull($component, 'Inertia component name should be resolved.');
            $this->assertStringStartsWith('Recipes', $component);
        });
    }
}

