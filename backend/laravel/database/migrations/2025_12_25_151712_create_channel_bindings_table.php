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
            $table->foreignId('node_channel_id')->constrained('node_channels')->cascadeOnDelete(); // Нормализовано через node_channels
            $table->enum('direction', ['actuator', 'sensor']);
            $table->string('role'); // main_pump|drain_pump|mister|fan|heater|ph_sensor|ec_sensor|...
            $table->timestamps();

            // Уникальность: один канал не может быть привязан к одному экземпляру инфраструктуры дважды
            $table->unique(['infrastructure_instance_id', 'node_channel_id'], 'channel_bindings_unique');
            // Уникальность: один канал не может принадлежать двум инстансам
            $table->unique(['node_channel_id'], 'channel_bindings_node_channel_unique');
            $table->index(['infrastructure_instance_id'], 'channel_bindings_infrastructure_idx');
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

