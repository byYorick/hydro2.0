<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('zone_correction_configs', function (Blueprint $table): void {
            $table->unsignedInteger('last_applied_version')->nullable()->after('last_applied_at');
        });
    }

    public function down(): void
    {
        // Legacy zone_correction_configs is removed by authority cleanup.
        // Rolling this schema tweak back is intentionally a no-op.
    }
};
