<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('zone_process_calibrations')) {
            return;
        }

        DB::table('zone_process_calibrations')
            ->whereNull('transport_delay_sec')
            ->update(['transport_delay_sec' => 0]);

        DB::table('zone_process_calibrations')
            ->whereNull('settle_sec')
            ->update(['settle_sec' => 0]);

        DB::table('zone_process_calibrations')
            ->whereNull('confidence')
            ->update(['confidence' => 1.00]);

        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        DB::statement('ALTER TABLE zone_process_calibrations ALTER COLUMN transport_delay_sec SET DEFAULT 0');
        DB::statement('ALTER TABLE zone_process_calibrations ALTER COLUMN settle_sec SET DEFAULT 0');
        DB::statement('ALTER TABLE zone_process_calibrations ALTER COLUMN confidence SET DEFAULT 1.00');
    }

    public function down(): void
    {
        if (! Schema::hasTable('zone_process_calibrations') || DB::getDriverName() !== 'pgsql') {
            return;
        }

        DB::statement('ALTER TABLE zone_process_calibrations ALTER COLUMN transport_delay_sec DROP DEFAULT');
        DB::statement('ALTER TABLE zone_process_calibrations ALTER COLUMN settle_sec DROP DEFAULT');
        DB::statement('ALTER TABLE zone_process_calibrations ALTER COLUMN confidence DROP DEFAULT');
    }
};
