<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('greenhouse_automation_logic_profiles', function (Blueprint $table) {
            $table->id();
            $table->foreignId('greenhouse_id')->constrained()->cascadeOnDelete();
            $table->string('mode', 16);
            $table->json('subsystems');
            $table->json('command_plans')->nullable();
            $table->boolean('is_active')->default(false);
            $table->foreignId('created_by')->nullable()->constrained('users')->nullOnDelete();
            $table->foreignId('updated_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamps();

            $table->unique(['greenhouse_id', 'mode']);
            $table->index(['greenhouse_id', 'is_active']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('greenhouse_automation_logic_profiles');
    }
};
