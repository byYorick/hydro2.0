<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        DB::statement("ALTER TYPE sensors_type_enum ADD VALUE IF NOT EXISTS 'FLOW_RATE'");
        DB::statement("ALTER TYPE sensors_type_enum ADD VALUE IF NOT EXISTS 'PUMP_CURRENT'");
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        // Enum values cannot be removed safely in PostgreSQL.
    }
};
