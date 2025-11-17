<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('zones', function (Blueprint $table) {
            $table->id();
            $table->foreignId('greenhouse_id')->nullable()->constrained('greenhouses')->cascadeOnDelete();
            $table->string('name');
            $table->text('description')->nullable();
            $table->string('status')->default('offline'); // online/offline/warning/critical
            $table->timestamps();
            $table->index('status', 'zones_status_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('zones');
    }
};


