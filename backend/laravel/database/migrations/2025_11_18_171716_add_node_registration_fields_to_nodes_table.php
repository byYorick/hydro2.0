<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::table('nodes', function (Blueprint $table) {
            // Добавляем поля для регистрации нод, если их еще нет
            if (!Schema::hasColumn('nodes', 'hardware_revision')) {
                $table->string('hardware_revision', 64)->nullable()->after('hardware_id');
            }
            if (!Schema::hasColumn('nodes', 'first_seen_at')) {
                $table->timestamp('first_seen_at')->nullable()->after('last_seen_at');
            }
            if (!Schema::hasColumn('nodes', 'last_heartbeat_at')) {
                $table->timestamp('last_heartbeat_at')->nullable()->after('first_seen_at');
            }
            if (!Schema::hasColumn('nodes', 'validated')) {
                $table->boolean('validated')->default(false)->after('lifecycle_state');
            }
            if (!Schema::hasColumn('nodes', 'uptime_seconds')) {
                $table->unsignedBigInteger('uptime_seconds')->nullable()->after('validated');
            }
            if (!Schema::hasColumn('nodes', 'free_heap_bytes')) {
                $table->unsignedInteger('free_heap_bytes')->nullable()->after('uptime_seconds');
            }
            if (!Schema::hasColumn('nodes', 'rssi')) {
                $table->integer('rssi')->nullable()->after('free_heap_bytes');
            }
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('nodes', function (Blueprint $table) {
            if (Schema::hasColumn('nodes', 'rssi')) {
                $table->dropColumn('rssi');
            }
            if (Schema::hasColumn('nodes', 'free_heap_bytes')) {
                $table->dropColumn('free_heap_bytes');
            }
            if (Schema::hasColumn('nodes', 'uptime_seconds')) {
                $table->dropColumn('uptime_seconds');
            }
            if (Schema::hasColumn('nodes', 'validated')) {
                $table->dropColumn('validated');
            }
            if (Schema::hasColumn('nodes', 'last_heartbeat_at')) {
                $table->dropColumn('last_heartbeat_at');
            }
            if (Schema::hasColumn('nodes', 'first_seen_at')) {
                $table->dropColumn('first_seen_at');
            }
            if (Schema::hasColumn('nodes', 'hardware_revision')) {
                $table->dropColumn('hardware_revision');
            }
        });
    }
};
