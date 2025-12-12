<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;

class E2eUserSeeder extends Seeder
{
    /**
     * Run the database seeds.
     *
     * Important: E2E needs deterministic credentials. We always (re)set the password
     * so repeated runs don't get stuck with an unknown previous password.
     */
    public function run(): void
    {
        User::updateOrCreate(
            ['email' => 'e2e@example.com'],
            [
                'name' => 'E2E User',
                // Keep in sync with tools/testing/run_e2e.sh
                'password' => Hash::make('e2e'),
                'role' => 'operator',
                'email_verified_at' => now(),
            ]
        );
    }
}


