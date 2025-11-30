<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('greenhouses', function (Blueprint $table) {
            $table->id();
            $table->string('uid', 64)->unique();
            $table->string('name');
            $table->string('timezone')->nullable();
            $table->string('type')->nullable(); // GREENHOUSE | ROOM | FARM
            $table->json('coordinates')->nullable();
            $table->text('description')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('greenhouses');
    }
};


