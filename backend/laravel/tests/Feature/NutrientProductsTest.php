<?php

namespace Tests\Feature;

use App\Models\NutrientProduct;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use Tests\RefreshDatabase;
use Tests\TestCase;

class NutrientProductsTest extends TestCase
{
    use RefreshDatabase;

    private function token(string $role = 'operator'): string
    {
        $user = User::factory()->create(['role' => $role]);
        $this->actingAs($user);

        return $user->createToken('test')->plainTextToken;
    }

    public function test_nutrient_products_requires_auth(): void
    {
        $this->getJson('/api/nutrient-products')->assertStatus(401);
    }

    public function test_nutrient_products_returns_list_and_supports_component_filter(): void
    {
        $token = $this->token('viewer');

        NutrientProduct::query()->create([
            'manufacturer' => 'Yara',
            'name' => 'YaraRega Water-Soluble NPK',
            'component' => 'npk',
            'composition' => 'NPK',
        ]);
        NutrientProduct::query()->create([
            'manufacturer' => 'Yara',
            'name' => 'YaraLiva Calcinit',
            'component' => 'calcium',
            'composition' => 'CaN',
        ]);

        $all = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson('/api/nutrient-products');

        $all->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonCount(2, 'data');

        $filtered = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson('/api/nutrient-products?component=npk');

        $filtered->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.component', 'npk')
            ->assertJsonPath('data.0.name', 'YaraRega Water-Soluble NPK');
    }

    public function test_operator_can_create_update_show_and_delete_nutrient_product(): void
    {
        $token = $this->token('operator');

        $create = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson('/api/nutrient-products', [
                'manufacturer' => 'Yara',
                'name' => 'YaraTera Kristalon 18-18-18',
                'component' => 'npk',
                'composition' => 'NPK 18-18-18',
                'recommended_stage' => 'VEG',
                'notes' => 'Тестовая запись',
                'metadata' => [
                    'source_url' => 'https://example.test/product',
                ],
            ]);

        $create->assertCreated()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.manufacturer', 'Yara')
            ->assertJsonPath('data.component', 'npk');

        $id = $create->json('data.id');
        $this->assertNotNull($id);

        $show = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/nutrient-products/{$id}");

        $show->assertOk()
            ->assertJsonPath('data.id', $id)
            ->assertJsonPath('data.name', 'YaraTera Kristalon 18-18-18');

        $update = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/nutrient-products/{$id}", [
                'component' => 'calcium',
                'name' => 'YaraLiva Calcinit',
            ]);

        $update->assertOk()
            ->assertJsonPath('data.component', 'calcium')
            ->assertJsonPath('data.name', 'YaraLiva Calcinit');

        $delete = $this->withHeader('Authorization', 'Bearer '.$token)
            ->deleteJson("/api/nutrient-products/{$id}");

        $delete->assertOk()
            ->assertJsonPath('status', 'ok');
        $this->assertDatabaseMissing('nutrient_products', ['id' => $id]);
    }

    public function test_cannot_create_duplicate_nutrient_product_combination(): void
    {
        $token = $this->token('operator');

        NutrientProduct::query()->create([
            'manufacturer' => 'Yara',
            'name' => 'YaraRega',
            'component' => 'npk',
            'composition' => 'NPK',
        ]);

        $duplicate = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson('/api/nutrient-products', [
                'manufacturer' => 'Yara',
                'name' => 'YaraRega',
                'component' => 'npk',
            ]);

        $duplicate->assertStatus(422)
            ->assertJsonValidationErrors(['unique_key']);
    }

    public function test_cannot_delete_product_that_is_referenced_in_recipe_phase(): void
    {
        $token = $this->token('operator');

        $product = NutrientProduct::query()->create([
            'manufacturer' => 'Yara',
            'name' => 'YaraLiva Calcinit',
            'component' => 'calcium',
            'composition' => '15.5-0-0 + 19% Ca',
        ]);

        RecipeRevisionPhase::factory()->create([
            'nutrient_calcium_product_id' => $product->id,
        ]);

        $delete = $this->withHeader('Authorization', 'Bearer '.$token)
            ->deleteJson("/api/nutrient-products/{$product->id}");

        $delete->assertStatus(422)
            ->assertJsonPath('status', 'error');
        $this->assertDatabaseHas('nutrient_products', ['id' => $product->id]);
    }
}
