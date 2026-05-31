<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public $withinTransaction = false;

    public function up(): void
    {
        DB::statement(<<<'SQL'
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sensors_type_enum') THEN
                    ALTER TYPE sensors_type_enum ADD VALUE IF NOT EXISTS 'OUTSIDE_TEMP';
                    ALTER TYPE sensors_type_enum ADD VALUE IF NOT EXISTS 'OUTSIDE_HUMIDITY';
                    ALTER TYPE sensors_type_enum ADD VALUE IF NOT EXISTS 'OUTSIDE_PRESSURE';
                    ALTER TYPE sensors_type_enum ADD VALUE IF NOT EXISTS 'OUTSIDE_LIGHT';
                    ALTER TYPE sensors_type_enum ADD VALUE IF NOT EXISTS 'RAIN_DETECTED';
                    ALTER TYPE sensors_type_enum ADD VALUE IF NOT EXISTS 'SOIL_TEMP';
                END IF;
            END $$;
        SQL);
    }

    public function down(): void
    {
        // PostgreSQL enum values cannot be removed safely.
    }
};
