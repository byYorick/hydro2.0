<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('commands_archive')) {
            Schema::create('commands_archive', function (Blueprint $table): void {
                $table->id();
                $table->foreignId('zone_id')->nullable()->constrained('zones')->nullOnDelete();
                $table->foreignId('node_id')->nullable()->constrained('nodes')->nullOnDelete();
                $table->string('channel')->nullable();
                $table->string('cmd');
                $table->jsonb('params')->nullable();
                $table->string('status')->default('pending');
                $table->string('cmd_id')->unique();
                $table->timestamp('created_at');
                $table->timestamp('sent_at')->nullable();
                $table->timestamp('ack_at')->nullable();
                $table->timestamp('failed_at')->nullable();
                $table->timestamp('archived_at')->useCurrent();

                $table->index('status', 'commands_archive_status_idx');
                $table->index('cmd_id', 'commands_archive_cmd_id_idx');
                $table->index(['zone_id', 'archived_at'], 'commands_archive_zone_archived_idx');
                $table->index('archived_at', 'commands_archive_archived_at_idx');
            });
        }

        if (! Schema::hasTable('zone_events_archive')) {
            Schema::create('zone_events_archive', function (Blueprint $table): void {
                $table->id();
                $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
                $table->string('type');
                $table->jsonb('details')->nullable();
                $table->timestamp('created_at');
                $table->timestamp('archived_at')->useCurrent();

                $table->index(['zone_id', 'archived_at'], 'zone_events_archive_zone_archived_idx');
                $table->index('type', 'zone_events_archive_type_idx');
                $table->index('archived_at', 'zone_events_archive_archived_at_idx');
            });
        }
    }

    public function down(): void
    {
        Schema::dropIfExists('commands_archive');
        Schema::dropIfExists('zone_events_archive');
    }
};
