<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('nodes', function (Blueprint $table) {
            $table->timestamp('pending_zone_set_at')->nullable()->after('pending_zone_id');
            $table->index('pending_zone_set_at', 'nodes_pending_zone_set_at_idx');
        });

        // Backfill: legacy pending binds без якоря TTL — proxy через updated_at.
        // После этого ExpirePendingNodeBindings опирается только на pending_zone_set_at.
        DB::table('nodes')
            ->whereNotNull('pending_zone_id')
            ->whereNull('pending_zone_set_at')
            ->update(['pending_zone_set_at' => DB::raw('updated_at')]);
    }

    public function down(): void
    {
        Schema::table('nodes', function (Blueprint $table) {
            $table->dropIndex('nodes_pending_zone_set_at_idx');
            $table->dropColumn('pending_zone_set_at');
        });
    }
};
