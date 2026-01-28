<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        if (! Schema::hasTable('pending_status_updates')) {
            Schema::create('pending_status_updates', function (Blueprint $table) {
                $table->bigIncrements('id');
                $table->string('cmd_id', 64);
                $table->string('status', 16);
                $table->jsonb('details')->nullable();
                $table->integer('retry_count')->default(0);
                $table->integer('max_attempts')->default(10);
                $table->timestampTz('next_retry_at')->nullable();
                $table->text('last_error')->nullable();
                $table->timestampTz('moved_to_dlq_at')->nullable();
                $table->timestampTz('created_at')->useCurrent();
                $table->timestampTz('updated_at')->useCurrent();
                $table->unique(['cmd_id', 'status'], 'pending_status_updates_cmd_status_unique');
            });
        }

        if (Schema::hasTable('pending_status_updates')) {
            DB::statement('CREATE INDEX IF NOT EXISTS idx_pending_status_retry ON pending_status_updates(next_retry_at) WHERE next_retry_at IS NOT NULL');
            DB::statement('CREATE INDEX IF NOT EXISTS idx_pending_status_cmd_id ON pending_status_updates(cmd_id)');
        }

        if (! Schema::hasTable('pending_status_updates_dlq')) {
            Schema::create('pending_status_updates_dlq', function (Blueprint $table) {
                $table->bigIncrements('id');
                $table->string('cmd_id', 64);
                $table->string('status', 16);
                $table->jsonb('details')->nullable();
                $table->integer('retry_count');
                $table->integer('max_attempts')->nullable();
                $table->text('last_error')->nullable();
                $table->timestampTz('failed_at')->useCurrent();
                $table->timestampTz('moved_to_dlq_at')->useCurrent();
                $table->unsignedBigInteger('original_id')->nullable();
                $table->timestampTz('created_at')->useCurrent();
            });
        }

        if (Schema::hasTable('pending_status_updates_dlq')) {
            DB::statement('CREATE INDEX IF NOT EXISTS idx_status_dlq_cmd_id ON pending_status_updates_dlq(cmd_id)');
            DB::statement('CREATE INDEX IF NOT EXISTS idx_status_dlq_failed_at ON pending_status_updates_dlq(failed_at)');
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('pending_status_updates_dlq');
        Schema::dropIfExists('pending_status_updates');
    }
};
