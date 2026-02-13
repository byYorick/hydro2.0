<?php

namespace Tests\Feature;

use App\Models\User;
use Tests\RefreshDatabase;
use Tests\TestCase;

class DashboardAccessTest extends TestCase
{
    use RefreshDatabase;

    public function test_engineer_can_open_dashboard(): void
    {
        $engineer = User::factory()->create([
            'role' => 'engineer',
        ]);

        $response = $this->actingAs($engineer)->get('/');

        $response->assertOk();
    }
}

