<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        DB::statement('CREATE SEQUENCE IF NOT EXISTS ae_claim_generation_seq AS bigint');
        DB::statement(<<<'SQL'
            SELECT setval('ae_claim_generation_seq', GREATEST(
                (SELECT COALESCE(MAX(claim_generation), 0) FROM ae_tasks),
                (SELECT COALESCE(MAX(claim_generation), 0) FROM ae_zone_leases),
                (SELECT last_value FROM ae_claim_generation_seq)
            ) + 1, false)
            SQL);
    }

    public function down(): void
    {
        DB::statement('DROP SEQUENCE IF EXISTS ae_claim_generation_seq');
    }
};
