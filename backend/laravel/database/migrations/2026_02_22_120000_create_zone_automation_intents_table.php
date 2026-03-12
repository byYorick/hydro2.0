<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('zone_automation_intents')) {
            Schema::create('zone_automation_intents', function (Blueprint $table) {
                $table->id();
                $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
                $table->string('intent_type', 64);
                $table->jsonb('payload')->nullable();
                $table->string('idempotency_key', 191);
                $table->string('status', 32)->default('pending');
                $table->timestampTz('not_before')->nullable();
                $table->timestampTz('claimed_at')->nullable();
                $table->timestampTz('completed_at')->nullable();
                $table->string('error_code', 128)->nullable();
                $table->text('error_message')->nullable();
                $table->unsignedInteger('retry_count')->default(0);
                $table->unsignedInteger('max_retries')->default(3);
                $table->timestampsTz();

                $table->unique('idempotency_key', 'zone_automation_intents_idempotency_key_unique');
                $table->index(['zone_id', 'status'], 'zone_automation_intents_zone_status_idx');
                $table->index(['status', 'not_before'], 'zone_automation_intents_status_not_before_idx');
            });
        }

        if (DB::getDriverName() === 'pgsql') {
            DB::statement(
                "DO $$
                 BEGIN
                     ALTER TABLE zone_automation_intents
                     ADD CONSTRAINT zone_automation_intents_status_check
                     CHECK (status IN ('pending','claimed','running','completed','failed','cancelled'));
                 EXCEPTION
                     WHEN duplicate_object THEN NULL;
                 END $$;"
            );
        }
    }

    public function down(): void
    {
        if (DB::getDriverName() === 'pgsql') {
            try {
                DB::statement(
                    'ALTER TABLE zone_automation_intents DROP CONSTRAINT IF EXISTS zone_automation_intents_status_check'
                );
            } catch (\Throwable) {
            }
        }

        Schema::dropIfExists('zone_automation_intents');
    }
};
