<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;

class SmartIrrigationE2ESeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Smart irrigation E2E dataset ===');

        $this->call(AdminUserSeeder::class);
        $this->call(PresetSeeder::class);
        $this->call(AutomationEngineE2ESeeder::class);

        $this->command->info('=== Smart irrigation E2E dataset complete ===');
    }
}
