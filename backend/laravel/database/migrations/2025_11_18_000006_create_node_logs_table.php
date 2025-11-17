<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('node_logs', function (Blueprint $table) {
            $table->id();
            $table->foreignId('node_id')->constrained('nodes')->cascadeOnDelete();
            $table->string('level'); // debug, info, warning, error, critical
            $table->text('message');
            $table->jsonb('context')->nullable();
            $table->timestamp('created_at')->useCurrent();

            $table->index(['node_id', 'created_at'], 'node_logs_node_created_idx');
            $table->index('level', 'node_logs_level_idx');
            $table->index('created_at', 'node_logs_created_at_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('node_logs');
    }
};

