<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('node_channels', function (Blueprint $table) {
            $table->id();
            $table->foreignId('node_id')->constrained('nodes')->cascadeOnDelete();
            $table->string('channel');
            $table->string('type')->nullable(); // sensor/actuator
            $table->string('metric')->nullable(); // PH, EC, TEMP_AIR...
            $table->string('unit')->nullable();
            $table->jsonb('config')->nullable();
            $table->timestamps();
            $table->unique(['node_id', 'channel']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('node_channels');
    }
};


