<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;

class DevBootstrapSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Dev bootstrap dataset ===');

        $this->call([
            AdminUserSeeder::class,
            PresetSeeder::class,
            PlantTaxonomySeeder::class,
            ZoneProcessCalibrationDefaultsSeeder::class,
        ]);

        $this->command->info('=== Dev bootstrap dataset complete ===');
    }
}
