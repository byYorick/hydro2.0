<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Привязка каналов к инфраструктуре (owner-agnostic)
     * Заменяет zone_channel_bindings
     */
    public function up(): void
    {
        Schema::create('channel_bindings', function (Blueprint $table) {
            $table->id();
            $table->foreignId('infrastructure_instance_id')->constrained('infrastructure_instances')->cascadeOnDelete();
            $table->foreignId('node_id')->constrained('nodes')->cascadeOnDelete();
            $table->string('channel'); // Строка как в NodeChannel
            $table->enum('direction', ['actuator', 'sensor']);
            $table->string('role'); // main_pump|drain_pump|mister|fan|heater|ph_sensor|ec_sensor|...
            $table->timestamps();

            // Уникальность: один канал ноды не может быть привязан к одному экземпляру инфраструктуры дважды
            $table->unique(['infrastructure_instance_id', 'node_id', 'channel'], 'channel_bindings_unique');
            $table->index(['infrastructure_instance_id'], 'channel_bindings_infrastructure_idx');
            $table->index(['node_id', 'channel'], 'channel_bindings_node_channel_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('channel_bindings');
    }
};

