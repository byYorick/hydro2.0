<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Привязка оборудования к нодам/каналам
     */
    public function up(): void
    {
        Schema::create('zone_channel_bindings', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->foreignId('asset_id')->constrained('zone_infrastructure')->cascadeOnDelete();
            $table->foreignId('node_id')->constrained('nodes')->cascadeOnDelete();
            $table->string('channel'); // Строка как в NodeChannel
            $table->string('direction'); // actuator|sensor
            $table->string('role'); // main_pump|drain_pump|mister|fan|heater|...
            $table->timestamps();
            
            $table->unique(['asset_id', 'node_id', 'channel'], 'zone_channel_bindings_unique');
            $table->index(['zone_id', 'asset_id']);
            $table->index(['node_id', 'channel']);
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('zone_channel_bindings');
    }
};

