<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Seeder;

class DatabaseSeeder extends Seeder
{
    /**
     * Seed the application's database.
     */
    public function run(): void
    {
        // Seed admin user
        $this->call(AdminUserSeeder::class);

        // Seed presets (plant growing presets)
        $this->call(PresetSeeder::class);

        // Seed demo data (only in development)
        if (app()->environment('local', 'development')) {
            $this->call(DemoDataSeeder::class);
            
            // Seed telemetry data (only in development, after demo data)
            // Используйте TelemetryMiniGraphSeeder для быстрого заполнения только миниграфиков
            // или TelemetrySeeder для полного набора данных
            if (config('app.telemetry_seeder_fast', false)) {
                $this->call(TelemetryMiniGraphSeeder::class);
            } else {
                $this->call(TelemetrySeeder::class);
            }
        }
    }
}
