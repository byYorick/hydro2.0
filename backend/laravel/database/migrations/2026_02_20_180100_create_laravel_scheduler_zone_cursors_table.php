<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('laravel_scheduler_zone_cursors', function (Blueprint $table) {
            $table->foreignId('zone_id')->primary()->constrained('zones')->cascadeOnDelete();
            $table->timestampTz('cursor_at');
            $table->string('catchup_policy', 32);
            $table->jsonb('metadata')->default(DB::raw("'{}'::jsonb"));
            $table->timestampsTz();

            $table->index('cursor_at', 'lszc_cursor_at_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('laravel_scheduler_zone_cursors');
    }
};

