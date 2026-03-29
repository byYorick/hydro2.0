<?php

namespace Tests\Feature;

use App\Models\Greenhouse;
use App\Models\User;
use Tests\RefreshDatabase;
use Tests\TestCase;

class GreenhouseControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_greenhouse_store_generates_unique_uid_when_requested_uid_already_exists(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);

        Greenhouse::factory()->create(['uid' => 'gh-main']);
        Greenhouse::factory()->create(['uid' => 'gh-main-2']);

        $response = $this->actingAs($user)->postJson('/api/greenhouses', [
            'uid' => 'gh-main',
            'name' => 'Main GH',
            'timezone' => 'Europe/Moscow',
        ]);

        $response->assertCreated()
            ->assertJsonPath('data.uid', 'gh-main-3')
            ->assertJsonPath('data.name', 'Main GH');

        $this->assertDatabaseHas('greenhouses', [
            'uid' => 'gh-main-3',
            'name' => 'Main GH',
        ]);
    }

    public function test_greenhouse_store_accepts_empty_string_greenhouse_type_id_as_null(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);

        $response = $this->actingAs($user)->postJson('/api/greenhouses', [
            'uid' => 'gh-no-type',
            'name' => 'No Type GH',
            'timezone' => 'Europe/Moscow',
            'greenhouse_type_id' => '',
        ]);

        $response->assertCreated()
            ->assertJsonPath('data.uid', 'gh-no-type')
            ->assertJsonPath('data.greenhouse_type_id', null);

        $this->assertDatabaseHas('greenhouses', [
            'uid' => 'gh-no-type',
            'name' => 'No Type GH',
        ]);
    }

    public function test_greenhouse_store_assigns_acl_and_makes_greenhouse_visible_in_index(): void
    {
        $creator = User::factory()->create(['role' => 'agronomist']);
        $viewer = User::factory()->create(['role' => 'viewer']);

        $response = $this->actingAs($creator)->postJson('/api/greenhouses', [
            'uid' => 'gh-acl-check',
            'name' => 'ACL GH',
            'timezone' => 'Europe/Moscow',
        ]);

        $response->assertCreated();
        $greenhouseId = (int) $response->json('data.id');

        $this->assertDatabaseHas('user_greenhouses', [
            'user_id' => $creator->id,
            'greenhouse_id' => $greenhouseId,
        ]);
        $this->assertDatabaseHas('user_greenhouses', [
            'user_id' => $viewer->id,
            'greenhouse_id' => $greenhouseId,
        ]);

        $this->actingAs($viewer)
            ->getJson('/api/greenhouses')
            ->assertOk()
            ->assertJsonPath('data.data.0.id', $greenhouseId)
            ->assertJsonPath('data.data.0.name', 'ACL GH');
    }
}
