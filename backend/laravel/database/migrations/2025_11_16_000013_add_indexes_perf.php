<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        DB::statement("CREATE INDEX IF NOT EXISTS commands_status_created_idx ON commands (status, created_at)");
        DB::statement("CREATE INDEX IF NOT EXISTS nodes_status_idx ON nodes (status)");
    }

    public function down(): void
    {
        DB::statement("DROP INDEX IF EXISTS commands_status_created_idx");
        DB::statement("DROP INDEX IF EXISTS nodes_status_idx");
    }
};


