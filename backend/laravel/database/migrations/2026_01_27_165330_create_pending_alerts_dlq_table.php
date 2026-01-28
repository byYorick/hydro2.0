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
        if (! Schema::hasTable('pending_alerts_dlq')) {
            Schema::create('pending_alerts_dlq', function (Blueprint $table) {
                $table->bigIncrements('id');
                $table->unsignedBigInteger('zone_id')->nullable();
                $table->string('source', 16);
                $table->string('code', 64);
                $table->string('type', 64);
                $table->string('status', 16);
                $table->jsonb('details')->nullable();
                $table->integer('attempts');
                $table->integer('max_attempts')->nullable();
                $table->text('last_error')->nullable();
                $table->timestampTz('failed_at')->useCurrent();
                $table->timestampTz('moved_to_dlq_at')->useCurrent();
                $table->unsignedBigInteger('original_id')->nullable();
                $table->timestampTz('created_at')->useCurrent();
            });
        }

        if (Schema::hasTable('pending_alerts_dlq')) {
            DB::statement('CREATE INDEX IF NOT EXISTS idx_alerts_dlq_zone_id ON pending_alerts_dlq(zone_id)');
            DB::statement('CREATE INDEX IF NOT EXISTS idx_alerts_dlq_failed_at ON pending_alerts_dlq(failed_at)');
            DB::statement('CREATE INDEX IF NOT EXISTS idx_alerts_dlq_code ON pending_alerts_dlq(code)');
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('pending_alerts_dlq');
    }
};
