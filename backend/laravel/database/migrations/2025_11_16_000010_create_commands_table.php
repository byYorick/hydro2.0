<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('commands', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->nullable()->constrained('zones')->nullOnDelete();
            $table->foreignId('node_id')->nullable()->constrained('nodes')->nullOnDelete();
            $table->string('channel')->nullable();
            $table->string('cmd');
            $table->jsonb('params')->nullable();
            $table->string('status')->default('pending'); // pending/sent/ack/failed/timeout
            $table->string('cmd_id')->unique();
            $table->timestamps();
            $table->timestamp('sent_at')->nullable();
            $table->timestamp('ack_at')->nullable();
            $table->timestamp('failed_at')->nullable();
            $table->index('status', 'commands_status_idx');
            $table->index('cmd_id', 'commands_cmd_id_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('commands');
    }
};


