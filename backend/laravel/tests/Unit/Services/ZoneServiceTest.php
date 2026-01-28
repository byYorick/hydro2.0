<?php

namespace Tests\Unit\Services;

use App\Models\DeviceNode;
use App\Models\GrowCycle;
use App\Models\RecipeRevision;
use App\Models\Zone;
use App\Services\ZoneService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneServiceTest extends TestCase
{
    use RefreshDatabase;

    private ZoneService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = new ZoneService;
    }

    public function test_create_zone(): void
    {
        $data = [
            'name' => 'Test Zone',
            'description' => 'Test Description',
            'status' => 'RUNNING',
        ];

        $zone = $this->service->create($data);

        $this->assertInstanceOf(Zone::class, $zone);
        $this->assertEquals('Test Zone', $zone->name);
        $this->assertEquals('RUNNING', $zone->status);
        $this->assertDatabaseHas('zones', [
            'id' => $zone->id,
            'name' => 'Test Zone',
        ]);
    }

    public function test_update_zone(): void
    {
        $zone = Zone::factory()->create(['name' => 'Old Name']);

        $updated = $this->service->update($zone, ['name' => 'New Name']);

        $this->assertEquals('New Name', $updated->name);
        $this->assertDatabaseHas('zones', [
            'id' => $zone->id,
            'name' => 'New Name',
        ]);
    }

    public function test_delete_zone_without_dependencies(): void
    {
        $zone = Zone::factory()->create();

        $this->service->delete($zone);

        $this->assertDatabaseMissing('zones', ['id' => $zone->id]);
    }

    public function test_delete_zone_with_active_recipe_throws_exception(): void
    {
        $zone = Zone::factory()->create();
        $revision = RecipeRevision::factory()->create();
        GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => \App\Enums\GrowCycleStatus::PLANNED,
        ]);

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Cannot delete zone with active grow cycle');

        $this->service->delete($zone);
    }

    public function test_delete_zone_with_attached_nodes_throws_exception(): void
    {
        $zone = Zone::factory()->create();
        DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Cannot delete zone with attached nodes');

        $this->service->delete($zone);
    }

    public function test_pause_zone(): void
    {
        $zone = Zone::factory()->create(['status' => 'RUNNING']);

        $paused = $this->service->pause($zone);

        $this->assertEquals('PAUSED', $paused->status);
    }

    public function test_pause_already_paused_zone_throws_exception(): void
    {
        $zone = Zone::factory()->create(['status' => 'PAUSED']);

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Zone is already paused');

        $this->service->pause($zone);
    }

    public function test_resume_zone(): void
    {
        $zone = Zone::factory()->create(['status' => 'PAUSED']);

        $resumed = $this->service->resume($zone);

        $this->assertEquals('RUNNING', $resumed->status);
    }

    public function test_resume_not_paused_zone_throws_exception(): void
    {
        $zone = Zone::factory()->create(['status' => 'RUNNING']);

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Zone is not paused');

        $this->service->resume($zone);
    }
}
