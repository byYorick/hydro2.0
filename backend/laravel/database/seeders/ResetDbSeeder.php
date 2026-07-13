<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;

/**
 * Минимальный seed после make reset-db:
 * базовые пользователи + system automation defaults + ACL bootstrap.
 */
class ResetDbSeeder extends Seeder
{
    public function run(): void
    {
        $this->call([
            StartUsersSeeder::class,
            AutomationAuthoritySystemDefaultsSeeder::class,
            AccessControlBootstrapSeeder::class,
        ]);
    }
}
