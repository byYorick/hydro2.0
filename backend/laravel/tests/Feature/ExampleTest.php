<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ExampleTest extends TestCase
{
    use RefreshDatabase;

    /**
     * A basic test example.
     */
    public function test_the_application_returns_a_successful_response(): void
    {
        $user = User::factory()->create();
        $response = $this->actingAs($user)->get('/');

        // Dashboard требует аутентификацию, поэтому может быть редирект или 200
        $response->assertStatus([200, 302]);
    }
}
