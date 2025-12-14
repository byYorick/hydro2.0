<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('pending_alerts', function (Blueprint $table) {
            $table->id();
            $table->unsignedBigInteger('zone_id')->nullable();
            $table->string('source')->default('biz'); // biz / infra
            $table->string('code')->nullable();
            $table->string('type');
            $table->jsonb('details')->nullable();
            $table->integer('attempts')->default(0);
            $table->integer('max_attempts')->default(3);
            $table->timestamp('last_attempt_at')->nullable();
            $table->string('status')->default('pending'); // pending, failed, dlq
            $table->text('last_error')->nullable();
            $table->timestamps();
            
            // Индексы для эффективного поиска
            $table->index(['status', 'created_at'], 'pending_alerts_status_created_idx');
            $table->index(['status', 'attempts', 'last_attempt_at'], 'pending_alerts_retry_idx');
            $table->foreign('zone_id')->references('id')->on('zones')->nullOnDelete();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('pending_alerts');
    }
};

