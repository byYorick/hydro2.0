<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('ai_logs', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->nullable()->constrained('zones')->nullOnDelete();
            $table->string('action'); // predict, recommend, explain, diagnostics
            $table->jsonb('details')->nullable();
            $table->timestamp('created_at')->useCurrent();

            $table->index(['zone_id', 'created_at'], 'ai_logs_zone_created_idx');
            $table->index('action', 'ai_logs_action_idx');
            $table->index('created_at', 'ai_logs_created_at_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('ai_logs');
    }
};

