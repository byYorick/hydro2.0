<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('scheduler_logs', function (Blueprint $table) {
            $table->id();
            $table->string('task_name');
            $table->string('status'); // pending, running, completed, failed
            $table->jsonb('details')->nullable();
            $table->timestamp('created_at')->useCurrent();

            $table->index(['task_name', 'created_at'], 'scheduler_logs_task_created_idx');
            $table->index('status', 'scheduler_logs_status_idx');
            $table->index('created_at', 'scheduler_logs_created_at_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('scheduler_logs');
    }
};

