<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('system_logs', function (Blueprint $table) {
            $table->id();
            $table->string('level'); // debug, info, warning, error, critical
            $table->text('message');
            $table->jsonb('context')->nullable();
            $table->timestamp('created_at')->useCurrent();

            $table->index(['level', 'created_at'], 'system_logs_level_created_idx');
            $table->index('created_at', 'system_logs_created_at_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('system_logs');
    }
};

