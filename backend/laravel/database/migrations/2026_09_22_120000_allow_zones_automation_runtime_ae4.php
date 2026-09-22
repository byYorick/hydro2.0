<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * CHECK zones.automation_runtime допускает ae3 и ae4.
 * Откат возвращает прежний check только на ae3.
 */
return new class extends Migration
{
    public function up(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        DB::statement('ALTER TABLE zones DROP CONSTRAINT IF EXISTS zones_automation_runtime_check');
        DB::statement("
            ALTER TABLE zones
            ADD CONSTRAINT zones_automation_runtime_check
            CHECK (automation_runtime IN ('ae3', 'ae4'))
        ");
    }

    public function down(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        DB::statement('ALTER TABLE zones DROP CONSTRAINT IF EXISTS zones_automation_runtime_check');
        DB::statement("
            ALTER TABLE zones
            ADD CONSTRAINT zones_automation_runtime_check
            CHECK (automation_runtime IN ('ae3'))
        ");
    }
};
