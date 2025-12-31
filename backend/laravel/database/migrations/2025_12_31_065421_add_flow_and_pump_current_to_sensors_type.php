<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public $withinTransaction = false;

    /**
     * Run the migrations.
     */
    public function up(): void
    {
        DB::statement(<<<'SQL'
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sensors_type_enum') THEN
                    ALTER TYPE sensors_type_enum ADD VALUE IF NOT EXISTS 'FLOW_RATE';
                    ALTER TYPE sensors_type_enum ADD VALUE IF NOT EXISTS 'PUMP_CURRENT';
                END IF;
            END $$;
        SQL);
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        // Enum values cannot be removed safely in PostgreSQL.
    }
};
