<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('nodes', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->nullable()->constrained('zones')->nullOnDelete();
            $table->string('uid', 64)->unique();
            $table->string('name')->nullable();
            $table->string('type')->nullable(); // ph, ec, climate, irrig, light
            $table->string('fw_version')->nullable();
            $table->timestamp('last_seen_at')->nullable();
            $table->string('status')->default('offline'); // online/offline
            $table->jsonb('config')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('nodes');
    }
};


