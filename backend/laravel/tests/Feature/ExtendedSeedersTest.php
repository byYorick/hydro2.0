<?php

namespace Tests\Feature;

use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\GrowCycle;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\Zone;
use Database\Seeders\AdminUserSeeder;
use Database\Seeders\ExtendedGreenhousesZonesSeeder;
use Database\Seeders\ExtendedGrowStagesSeeder;
use Database\Seeders\ExtendedInfrastructureAssetsSeeder;
use Database\Seeders\ExtendedInfrastructureSeeder;
use Database\Seeders\ExtendedNodesChannelsSeeder;
use Database\Seeders\ExtendedRecipesCyclesSeeder;
use Database\Seeders\PlantTaxonomySeeder;
use Database\Seeders\PresetSeeder;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ExtendedSeedersTest extends TestCase
{
    use RefreshDatabase;

    public function test_extended_seeders_work_with_new_schema(): void
    {
        $this->seed([
            AdminUserSeeder::class,
            PresetSeeder::class,
            PlantTaxonomySeeder::class,
            ExtendedGreenhousesZonesSeeder::class,
            ExtendedInfrastructureAssetsSeeder::class,
            ExtendedNodesChannelsSeeder::class,
            ExtendedInfrastructureSeeder::class,
            ExtendedRecipesCyclesSeeder::class,
            ExtendedGrowStagesSeeder::class,
        ]);

        $this->assertGreaterThan(0, InfrastructureInstance::count());
        $this->assertGreaterThan(0, ChannelBinding::count());
        $this->assertGreaterThan(0, RecipeRevision::count());
        $this->assertGreaterThan(0, RecipeRevisionPhase::count());
        $this->assertGreaterThan(0, GrowCycle::count());
        $this->assertGreaterThan(0, NodeChannel::count());
        $this->assertGreaterThanOrEqual(Zone::count(), DeviceNode::count());
    }
}
