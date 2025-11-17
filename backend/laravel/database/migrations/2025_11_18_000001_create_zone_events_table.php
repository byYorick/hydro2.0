<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('zone_events', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->string('type');
            $table->jsonb('details')->nullable();
            $table->timestamp('created_at')->useCurrent();

            $table->index(['zone_id', 'created_at'], 'zone_events_zone_id_created_at_idx');
            $table->index('type', 'zone_events_type_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('zone_events');
    }
};

