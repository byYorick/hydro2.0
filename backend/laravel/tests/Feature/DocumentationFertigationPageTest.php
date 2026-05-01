<?php

namespace Tests\Feature;

use App\Models\User;
use Inertia\Testing\AssertableInertia;
use Tests\TestCase;

class DocumentationFertigationPageTest extends TestCase
{
    public function test_agronomist_can_view_documentation_inertia_page(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);

        $this->actingAs($user)
            ->get(route('documentation.fertigation'))
            ->assertStatus(200)
            ->assertInertia(function (AssertableInertia $page): void {
                $page->component('Documentation/Fertigation')
                    ->has('auth.user.role');
            });
    }

    public function test_viewer_cannot_view_documentation_page(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);

        $this->actingAs($user)
            ->get(route('documentation.fertigation'))
            ->assertStatus(403);
    }
}
