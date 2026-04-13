<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('substrates', function (Blueprint $table) {
            $table->id();
            $table->string('code', 64)->unique();
            $table->string('name', 128);
            // Массив компонентов: [{name, label, ratio_pct}]
            $table->jsonb('components')->default('[]');
            // Совместимые системы полива: ['drip_tape','drip_emitter','ebb_flow',...]
            $table->jsonb('applicable_systems')->default('[]');
            $table->text('notes')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('substrates');
    }
};
