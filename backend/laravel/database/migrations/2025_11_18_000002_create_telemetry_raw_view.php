<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        // Создаем VIEW telemetry_raw как алиас для telemetry_samples
        // Согласно DATA_RETENTION_POLICY.md, telemetry_raw используется для Hot Telemetry
        DB::statement('CREATE OR REPLACE VIEW telemetry_raw AS SELECT * FROM telemetry_samples;');
    }

    public function down(): void
    {
        DB::statement('DROP VIEW IF EXISTS telemetry_raw;');
    }
};

