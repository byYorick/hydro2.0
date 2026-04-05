<?php

namespace Tests\Feature;

use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\File;
use Inertia\Testing\AssertableInertia;
use Tests\RefreshDatabase;
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

    public function test_admin_can_delete_plant_via_api(): void
    {
        $user = $this->makeUser();
        $plant = Plant::factory()->create();

        $response = $this->actingAs($user)->deleteJson("/api/plants/{$plant->id}");

        $response->assertOk()
            ->assertJsonPath('status', 'ok');
        $this->assertDatabaseMissing('plants', ['id' => $plant->id]);
    }

    public function test_admin_can_create_plant_with_recipe_atomically(): void
    {
        $user = $this->makeUser();

        $payload = [
            'plant' => [
                'name' => 'Салат атомарный',
                'species' => 'Lactuca sativa',
                'growing_system' => 'drip',
                'substrate_type' => 'coco',
            ],
            'recipe' => [
                'name' => 'Салат атомарный — полный цикл',
                'description' => 'Создано в одном запросе',
                'revision_description' => 'Initial revision from test',
                'phases' => [
                    [
                        'phase_index' => 0,
                        'name' => 'Старт',
                        'duration_hours' => 72,
                        'ph_target' => 5.8,
                        'ph_min' => 5.7,
                        'ph_max' => 5.9,
                        'ec_target' => 1.4,
                        'ec_min' => 1.3,
                        'ec_max' => 1.5,
                        'temp_air_target' => 23,
                        'humidity_target' => 62,
                        'lighting_photoperiod_hours' => 16,
                        'lighting_start_time' => '06:00:00',
                        'irrigation_mode' => 'SUBSTRATE',
                        'irrigation_interval_sec' => 900,
                        'irrigation_duration_sec' => 15,
                        'extensions' => [
                            'day_night' => [
                                'ph' => ['day' => 5.8, 'night' => 5.8],
                                'ec' => ['day' => 1.4, 'night' => 1.4],
                                'temperature' => ['day' => 23, 'night' => 21],
                                'humidity' => ['day' => 62, 'night' => 66],
                                'lighting' => ['day_start_time' => '06:00:00', 'day_hours' => 16],
                            ],
                            'subsystems' => [
                                'irrigation' => [
                                    'targets' => [
                                        'system_type' => 'drip',
                                    ],
                                ],
                            ],
                        ],
                    ],
                ],
            ],
        ];

        $response = $this->actingAs($user)->postJson('/api/plants/with-recipe', $payload);

        $response->assertCreated()
            ->assertJsonPath('data.plant.name', 'Салат атомарный')
            ->assertJsonPath('data.recipe.name', 'Салат атомарный — полный цикл');

        $plant = Plant::query()->where('name', 'Салат атомарный')->firstOrFail();
        $recipe = Recipe::query()->where('name', 'Салат атомарный — полный цикл')->firstOrFail();
        $revision = RecipeRevision::query()->where('recipe_id', $recipe->id)->firstOrFail();
        $phase = RecipeRevisionPhase::query()->where('recipe_revision_id', $revision->id)->firstOrFail();

        $this->assertDatabaseHas('plants', ['id' => $plant->id, 'growing_system' => 'drip']);
        $this->assertDatabaseHas('recipe_revisions', ['id' => $revision->id, 'status' => 'PUBLISHED']);
        $this->assertSame('drip', data_get($phase->extensions, 'subsystems.irrigation.targets.system_type'));
        $this->assertSame('06:00:00', data_get($phase->extensions, 'day_night.lighting.day_start_time'));
    }

    public function test_create_plant_with_recipe_rejects_phase_target_outside_bounds(): void
    {
        $user = $this->makeUser();

        $payload = [
            'plant' => [
                'name' => 'Салат с невалидной фазой',
            ],
            'recipe' => [
                'name' => 'Рецепт с невалидной фазой',
                'phases' => [
                    [
                        'phase_index' => 0,
                        'name' => 'Фаза 1',
                        'duration_hours' => 72,
                        'ph_target' => 5.2,
                        'ph_min' => 5.3,
                        'ph_max' => 5.4,
                        'ec_target' => 1.4,
                        'ec_min' => 1.3,
                        'ec_max' => 1.5,
                    ],
                ],
            ],
        ];

        $response = $this->actingAs($user)->postJson('/api/plants/with-recipe', $payload);

        $response->assertStatus(422)
            ->assertJsonValidationErrors(['recipe.phases.0.ph_target']);

        $this->assertDatabaseMissing('plants', ['name' => 'Салат с невалидной фазой']);
        $this->assertDatabaseMissing('recipes', ['name' => 'Рецепт с невалидной фазой']);
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

    public function test_admin_can_update_plant_taxonomy(): void
    {
        $user = $this->makeUser();
        $path = base_path('config/plant_taxonomies.json');
        $original = File::exists($path) ? File::get($path) : null;

        try {
            $payload = [
                'items' => [
                    ['id' => 'coco', 'label' => 'Кокос'],
                    ['id' => 'rockwool', 'label' => 'Минвата'],
                ],
            ];

            $response = $this->actingAs($user)->putJson('/api/plant-taxonomies/substrate_type', $payload);

            $response->assertOk()
                ->assertJsonPath('data.key', 'substrate_type')
                ->assertJsonCount(2, 'data.items');

            $updated = json_decode(File::get($path), true);
            $this->assertSame('Кокос', $updated['substrate_type'][0]['label']);
        } finally {
            if ($original !== null) {
                File::put($path, $original);
            }
        }
    }

    private function makeUser(string $role = 'admin'): User
    {
        return User::factory()->create(['role' => $role]);
    }
}
