<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        DB::statement('UPDATE zones SET status = LOWER(status) WHERE status IS NOT NULL');
    }

    public function down(): void
    {
        // Irreversible data normalization migration.
    }
};
