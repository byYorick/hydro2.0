<?php

namespace Tests\Feature;

use App\Models\Plant;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Event;
use Inertia\Testing\AssertableInertia;
use Tests\TestCase;

class PlantsTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        Event::fake();
    }

    public function test_admin_can_view_plants_page(): void
    {
        $user = $this->makeUser();
        Plant::factory()->count(2)->create();

        $response = $this->actingAs($user)->get('/plants');

        $response->assertStatus(200)
            ->assertInertia(function (AssertableInertia $page) {
                $page->component('Plants/Index')
                    ->has('plants')
                    ->has('taxonomies');
            });
    }

    public function test_agronomist_can_view_plants_page(): void
    {
        $user = $this->makeUser('agronomist');
        Plant::factory()->create();

        $this->actingAs($user)
            ->get('/plants')
            ->assertStatus(200);
    }

    public function test_admin_can_create_plant(): void
    {
        $user = $this->makeUser();

        $payload = [
            'name' => 'Тестовая культура',
            'species' => 'Test species',
            'variety' => 'Genovese',
            'substrate_type' => 'coco',
            'growing_system' => 'nft',
            'photoperiod_preset' => '16_8',
            'seasonality' => 'all_year',
            'description' => 'Описание растения',
            'environment_requirements' => [
                'temperature' => ['min' => 20, 'max' => 26],
                'ph' => ['min' => 5.5, 'max' => 6.2],
            ],
        ];

        $response = $this->actingAs($user)->post('/plants', $payload);

        $response->assertRedirect();
        $this->assertDatabaseHas('plants', [
            'name' => 'Тестовая культура',
            'substrate_type' => 'coco',
            'growing_system' => 'nft',
        ]);
    }

    public function test_admin_can_update_plant(): void
    {
        $user = $this->makeUser();
        $plant = Plant::factory()->create(['name' => 'Старое имя']);

        $response = $this->actingAs($user)->put("/plants/{$plant->id}", [
            'name' => 'Обновлённое имя',
            'slug' => $plant->slug,
            'substrate_type' => 'perlite',
            'growing_system' => 'drip',
            'photoperiod_preset' => '18_6',
            'seasonality' => 'multi_cycle',
            'description' => 'Обновлённое описание',
            'environment_requirements' => [
                'temperature' => ['min' => 19, 'max' => 25],
            ],
        ]);

        $response->assertRedirect();
        $this->assertDatabaseHas('plants', [
            'id' => $plant->id,
            'name' => 'Обновлённое имя',
            'substrate_type' => 'perlite',
        ]);
    }

    public function test_admin_can_add_price_version(): void
    {
        $user = $this->makeUser();
        $plant = Plant::factory()->create();

        $response = $this->actingAs($user)->post("/plants/{$plant->id}/prices", [
            'effective_from' => now()->toDateString(),
            'seedling_cost' => 10,
            'substrate_cost' => 5,
            'wholesale_price' => 40,
            'retail_price' => 60,
        ]);

        $response->assertRedirect();
        $this->assertDatabaseHas('plant_price_versions', [
            'plant_id' => $plant->id,
            'wholesale_price' => 40,
            'retail_price' => 60,
        ]);
    }

    public function test_profitability_endpoint_returns_data(): void
    {
        $user = $this->makeUser();
        $plant = Plant::factory()->create();
        $plant->priceVersions()->create([
            'currency' => 'RUB',
            'seedling_cost' => 10,
            'substrate_cost' => 5,
            'wholesale_price' => 40,
            'retail_price' => 60,
        ]);

        $response = $this->actingAs($user)->getJson("/api/profitability/plants/{$plant->id}");

        $response->assertOk()
            ->assertJsonPath('data.plant_id', $plant->id)
            ->assertJsonPath('data.total_cost', 15.0)
            ->assertJsonPath('data.margin_retail', 45.0);
    }

    private function makeUser(string $role = 'admin'): User
    {
        return User::factory()->create(['role' => $role]);
    }
}

