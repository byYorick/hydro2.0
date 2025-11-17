<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('alerts', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->nullable()->constrained('zones')->nullOnDelete();
            $table->string('type');
            $table->jsonb('details')->nullable();
            $table->string('status')->default('ACTIVE'); // ACTIVE/RESOLVED
            $table->timestamp('created_at')->useCurrent();
            $table->timestamp('resolved_at')->nullable();
            $table->index(['zone_id', 'status'], 'alerts_zone_status_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('alerts');
    }
};


