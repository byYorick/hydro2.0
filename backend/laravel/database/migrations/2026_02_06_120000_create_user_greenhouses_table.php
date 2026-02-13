<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('user_greenhouses', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->foreignId('greenhouse_id')->constrained()->cascadeOnDelete();
            $table->timestamps();

            $table->unique(['user_id', 'greenhouse_id'], 'user_greenhouses_unique');
            $table->index(['greenhouse_id', 'user_id'], 'user_greenhouses_greenhouse_user_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('user_greenhouses');
    }
};
