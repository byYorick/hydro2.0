<?php

namespace Tests\Feature;

use App\Models\User;
use App\Services\ZoneAutomationPresetService;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationPresetDefaultDripMigrationTest extends TestCase
{
    use RefreshDatabase;

    public function test_seeded_default_dwc_becomes_drip_and_named_dwc_presets_stay(): void
    {
        $this->assertSame('drip', $this->columnDefault());
        $this->assertSame('dwc', $this->typeOf('dwc-balanced'));
        $this->assertSame('dwc', $this->typeOf('dwc-safe'));
        $this->assertSame('dwc', $this->typeOf('dwc-aggressive'));
        $this->assertSame('drip', $this->typeOf('test-node-automation'));
        $this->assertSame('nft', $this->typeOf('nft-balanced'));
        $this->assertSame('drip_tape', $this->typeOf('drip-tape-balanced'));

        $migration = require database_path('migrations/2026_11_09_170000_default_zone_preset_system_type_to_drip.php');
        $migration->down();

        $this->assertSame('dwc', $this->columnDefault());
        $this->assertSame('dwc', $this->typeOf('test-node-automation'));
        $this->assertSame('dwc', $this->typeOf('dwc-balanced'));
        $this->assertFalse(Schema::hasTable('zone_automation_preset_dwc_default_rewrites'));

        $this->insertPreset('lettuce-default', 'Lettuce', 'dwc');
        $this->insertPreset('my-dwc-bed', 'DWC bed', 'dwc');

        $migration->up();

        $this->assertSame('drip', $this->columnDefault());
        $this->assertSame('drip', $this->typeOf('test-node-automation'));
        $this->assertSame('drip', $this->typeOf('lettuce-default'));
        $this->assertSame('dwc', $this->typeOf('my-dwc-bed'));
        $this->assertSame('dwc', $this->typeOf('dwc-balanced'));

        $migration->down();

        $this->assertSame('dwc', $this->typeOf('lettuce-default'));
        $this->assertSame('dwc', $this->typeOf('test-node-automation'));
        $this->assertSame('dwc', $this->typeOf('my-dwc-bed'));
    }

    public function test_catalog_endpoint_lists_implemented_drip(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);

        $this->actingAs($user)
            ->getJson('/api/hydroponic-systems')
            ->assertOk()
            ->assertJsonPath('data.implemented', ['drip'])
            ->assertJsonPath('data.canonical', ['drip', 'ebb_flow', 'nft', 'dwc'])
            ->assertJsonPath('data.needs_review', ['substrate', 'substrate_trays', 'aeroponics']);
    }

    public function test_service_omitted_type_defaults_to_drip(): void
    {
        $preset = app(ZoneAutomationPresetService::class)->create([
            'name' => 'Без явного типа',
            'tanks_count' => 2,
            'config' => [],
        ]);

        $this->assertSame('drip', $preset->irrigation_system_type);
    }

    private function typeOf(string $slug): ?string
    {
        $value = DB::table('zone_automation_presets')->where('slug', $slug)->value('irrigation_system_type');

        return is_string($value) ? $value : null;
    }

    private function columnDefault(): string
    {
        $row = DB::selectOne(
            "SELECT column_default FROM information_schema.columns
             WHERE table_name = 'zone_automation_presets' AND column_name = 'irrigation_system_type'"
        );

        return str_contains((string) ($row->column_default ?? ''), 'drip') ? 'drip' : 'dwc';
    }

    private function insertPreset(string $slug, string $name, string $systemType): void
    {
        DB::table('zone_automation_presets')->insert([
            'name' => $name,
            'slug' => $slug,
            'description' => 'custom',
            'scope' => 'custom',
            'is_locked' => false,
            'tanks_count' => 2,
            'irrigation_system_type' => $systemType,
            'config' => json_encode([]),
            'created_at' => now(),
            'updated_at' => now(),
        ]);
    }
}
