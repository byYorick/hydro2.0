<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('zone_events_archive', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->string('type');
            $table->jsonb('details')->nullable();
            $table->timestamp('created_at');
            $table->timestamp('archived_at')->useCurrent(); // Время архивирования

            $table->index(['zone_id', 'archived_at'], 'zone_events_archive_zone_archived_idx');
            $table->index('type', 'zone_events_archive_type_idx');
            $table->index('archived_at', 'zone_events_archive_archived_at_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('zone_events_archive');
    }
};

