<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('user_zones', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->foreignId('zone_id')->constrained()->cascadeOnDelete();
            $table->timestamps();

            $table->unique(['user_id', 'zone_id'], 'user_zones_unique');
            $table->index(['zone_id', 'user_id'], 'user_zones_zone_user_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('user_zones');
    }
};
