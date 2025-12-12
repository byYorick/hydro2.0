<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Создает таблицу архива для unassigned_node_errors.
     * Используется для аудита и отслеживания истории ошибок,
     * которые были привязаны к нодам при регистрации.
     */
    public function up(): void
    {
        Schema::create('unassigned_node_errors_archive', function (Blueprint $table) {
            $table->id();
            $table->string('hardware_id')->index();
            $table->text('error_message');
            $table->string('error_code')->nullable();
            $table->string('severity')->default('ERROR');
            $table->string('topic');
            $table->jsonb('last_payload')->nullable();
            $table->integer('count')->default(1);
            $table->timestamp('first_seen_at');
            $table->timestamp('last_seen_at');
            $table->foreignId('node_id')->nullable()->constrained('nodes')->nullOnDelete();
            $table->timestamp('archived_at')->useCurrent(); // Время архивирования
            $table->timestamp('attached_at')->nullable(); // Время привязки к ноде
            $table->foreignId('attached_zone_id')->nullable()->constrained('zones')->nullOnDelete();

            $table->index('hardware_id', 'unassigned_errors_archive_hardware_id_idx');
            $table->index('node_id', 'unassigned_errors_archive_node_id_idx');
            $table->index('archived_at', 'unassigned_errors_archive_archived_at_idx');
            $table->index(['hardware_id', 'error_code'], 'unassigned_errors_archive_hardware_code_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('unassigned_node_errors_archive');
    }
};

